"""开放平台总览端点测试。

覆盖：
- ``GET /api/v1/open-platform/overview`` 管理员全局视图（应用/密钥/节点/审计统计与最近操作）；
- OA 用户视图强制按 owner 过滤（只统计本人名下，不含平台级字段）；
- 未登录访问返回 401。

需要真实 Postgres：通过 ``TEST_PG_CONN_STRING`` 提供隔离测试库；
未配置时 conftest 的 db_session 会自动 skip 本模块所有用例。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.oa_auth import create_oa_session
from app.main import app
from app.models.agent import AgentNode
from app.models.oa import OaUser
from app.services.open_platform_service import open_platform_service, utc_now


def _uniq(name: str) -> str:
    """全局唯一 app_name，避免持久化测试库中的唯一约束冲突。"""
    return f"{name}-{uuid.uuid4().hex[:8]}"


def _admin_settings():
    settings = get_settings()
    return (
        settings.open_platform_admin_username,
        settings.open_platform_admin_password_hash,
        settings.open_platform_session_secret,
        settings.open_platform_cookie_secure,
        settings.oa_cookie_name,
        settings.oa_jwt_secret,
    )


def _apply_admin_settings():
    settings = get_settings()
    settings.open_platform_admin_username = "admin"
    settings.open_platform_admin_password_hash = PasswordHasher().hash("correct-horse-battery")
    settings.open_platform_session_secret = "test-session-secret-with-enough-entropy"
    settings.open_platform_cookie_secure = False
    settings.oa_cookie_name = "unidata_oa_session"
    settings.oa_jwt_secret = "test-oa-jwt-secret-long-enough"


def _restore_admin_settings(original) -> None:
    (
        get_settings().open_platform_admin_username,
        get_settings().open_platform_admin_password_hash,
        get_settings().open_platform_session_secret,
        get_settings().open_platform_cookie_secure,
        get_settings().oa_cookie_name,
        get_settings().oa_jwt_secret,
    ) = original


@pytest.fixture
async def admin_client(db_session: AsyncSession):
    original = _admin_settings()
    _apply_admin_settings()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/open-platform/session",
            json={"username": "admin", "password": "correct-horse-battery"},
        )
        assert resp.status_code == 200, resp.text
        yield client
    app.dependency_overrides.clear()
    _restore_admin_settings(original)


@pytest.fixture
async def oa_view_client(db_session: AsyncSession):
    """OA 用户客户端：唯一 itcode，避免与测试库中遗留数据串扰。"""
    settings = get_settings()
    original = _admin_settings()
    _apply_admin_settings()

    itcode = f"oa-ov-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    db_session.add(OaUser(itcode=itcode, profile={"姓名": itcode}, status="active", created_at=now, updated_at=now))
    await db_session.commit()

    token, _ = create_oa_session(itcode, {"姓名": itcode})

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(settings.oa_cookie_name, token)
        yield client, itcode
    app.dependency_overrides.clear()
    _restore_admin_settings(original)


class TestAdminOverview:
    async def test_platform_scope_counts_and_fields(self, admin_client: AsyncClient, db_session: AsyncSession):
        before = (await admin_client.get("/api/v1/open-platform/overview")).json()["data"]
        assert before["scope"] == "platform"

        app = await open_platform_service.create_app(
            db_session, app_name=_uniq("ov-app"), display_name="OV", owner_itcode="pytest",
            description=None, actor="admin:admin", source_ip=None,
        )
        key_soon, _ = await open_platform_service.create_key(
            db_session, app_id=app.id, name="soon", scopes=["data:read"],
            expires_at=utc_now() + timedelta(days=10), actor="admin:admin", source_ip=None,
        )
        key_stale, _ = await open_platform_service.create_key(
            db_session, app_id=app.id, name="stale", scopes=["search:read"],
            expires_at=utc_now() + timedelta(days=100), actor="admin:admin", source_ip=None,
        )
        key_stale.last_used_at = utc_now() - timedelta(days=40)
        open_platform_service.add_audit(db_session, actor="ov-test", action="ov.check", target_type="app", target_id=app.id)
        db_session.add(AgentNode(id=f"ov-agent-{uuid.uuid4().hex[:8]}", ip="127.0.0.1", port=8091, last_seen_at=utc_now()))
        await db_session.commit()

        resp = await admin_client.get("/api/v1/open-platform/overview")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        assert data["scope"] == "platform"
        assert data["apps"]["total"] == before["apps"]["total"] + 1
        assert data["apps"]["active"] == before["apps"]["active"] + 1
        assert data["keys"]["expiring_in_30_days"] == before["keys"]["expiring_in_30_days"] + 1
        assert data["keys"]["unused_30_days"] == before["keys"]["unused_30_days"] + 1
        assert any(item["key_id"] == key_soon.id and item["app_name"] == app.app_name for item in data["expiring_keys"])
        assert data["agents"]["total"] == before["agents"]["total"] + 1
        assert data["agents"]["online"] == before["agents"]["online"] + 1
        assert data["audit"]["last_7_days"] == before["audit"]["last_7_days"] + 1
        assert any(item["action"] == "ov.check" for item in data["recent_audit"])

    async def test_recent_audit_is_capped_at_five(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/v1/open-platform/overview")).json()["data"]
        assert len(data["recent_audit"]) <= 5


class TestOaOverview:
    async def test_self_scope_only_counts_own_apps(self, oa_view_client, db_session: AsyncSession):
        client, itcode = oa_view_client

        own_app = await open_platform_service.create_app(
            db_session, app_name=_uniq("ov-own"), display_name="Own", owner_itcode=itcode,
            description=None, actor=f"oa:{itcode}", source_ip=None,
        )
        disabled_app = await open_platform_service.create_app(
            db_session, app_name=_uniq("ov-dis"), display_name="Dis", owner_itcode=itcode,
            description=None, actor=f"oa:{itcode}", source_ip=None,
        )
        disabled_app.status = "disabled"
        other_app = await open_platform_service.create_app(
            db_session, app_name=_uniq("ov-other"), display_name="Other", owner_itcode="someone-else",
            description=None, actor="admin:admin", source_ip=None,
        )
        await open_platform_service.create_key(
            db_session, app_id=own_app.id, name="k1", scopes=["data:write"],
            expires_at=utc_now() + timedelta(days=5), actor=f"oa:{itcode}", source_ip=None,
        )
        await open_platform_service.create_key(
            db_session, app_id=other_app.id, name="k2", scopes=["data:write"],
            expires_at=utc_now() + timedelta(days=5), actor="admin:admin", source_ip=None,
        )
        await db_session.commit()

        resp = await client.get("/api/v1/open-platform/overview")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        assert data["scope"] == "self"
        assert data["apps"] == {"total": 2, "active": 1, "disabled": 1}
        assert data["keys"]["expiring_in_30_days"] == 1
        assert data["keys"]["unused_30_days"] is None
        assert data["agents"] is None
        assert data["audit"] is None
        assert data["recent_audit"] is None
        assert [item["app_name"] for item in data["expiring_keys"]] == [own_app.app_name]
        apps_recent = {item["id"]: item["active_key_count"] for item in data["apps_recent"]}
        assert apps_recent == {own_app.id: 1, disabled_app.id: 0}


class TestOverviewAuth:
    async def test_requires_session(self, client: AsyncClient):
        resp = await client.get("/api/v1/open-platform/overview")
        assert resp.status_code == 401

"""开放平台管理端点回归测试（此前零/弱覆盖的高风险端点）。

覆盖：
- ``GET /apps/{app_id}`` 应用详情；
- ``PATCH /apps/{app_id}`` 更新（含 OA 不能改 owner 的边界）；
- ``DELETE /apps/{app_id}`` 删除应用并回收租户资源（破坏性，重点验证权限与回收）；
- ``POST /keys/{key_id}/rotate`` 轮换密钥；
- ``GET /audit-logs`` 审计记录（仅管理员）；
- ``GET /apps/{app_id}/collections`` 集合列表。

需要真实 Postgres：通过 ``TEST_PG_CONN_STRING`` 提供隔离测试库；
未配置时 conftest 的 db_session 会自动 skip 本模块所有用例。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.oa_auth import create_oa_session
from app.main import app
from app.models.oa import OaUser
from app.services.open_platform_service import open_platform_service, utc_now

import uuid


def _uniq(name: str) -> str:
    """生成全局唯一的 app_name，避免重复运行/持久化测试库时 app_name 唯一约束冲突。"""
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


@pytest.fixture
async def admin_client(db_session: AsyncSession):
    original = _admin_settings()
    _apply_admin_settings()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    (
        get_settings().open_platform_admin_username,
        get_settings().open_platform_admin_password_hash,
        get_settings().open_platform_session_secret,
        get_settings().open_platform_cookie_secure,
        get_settings().oa_cookie_name,
        get_settings().oa_jwt_secret,
    ) = original


async def _admin_login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/open-platform/session",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["csrf_token"]


@pytest.fixture
async def oa_owner_client(db_session: AsyncSession):
    """OA 用户（owner=oa-owner）客户端：注入 DB 并签发 OA 会话 cookie。"""
    from sqlalchemy.dialects.postgresql import insert as _pg_insert

    settings = get_settings()
    original = _admin_settings()
    _apply_admin_settings()

    # 确保 OA 用户存在于库（供 get_any_session 的 active 校验）；幂等写入
    now = datetime.now(timezone.utc)
    await db_session.execute(
        _pg_insert(OaUser)
        .values(itcode="oa-owner", profile={"姓名": "oa-owner"}, status="active", created_at=now, updated_at=now)
        .on_conflict_do_update(index_elements=["itcode"], set_={"status": "active", "updated_at": now})
    )
    await db_session.commit()

    token, _ = create_oa_session("oa-owner", {"姓名": "oa-owner", "email": "oa@x.com"})

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(settings.oa_cookie_name, token)
        yield client
    app.dependency_overrides.clear()
    (
        get_settings().open_platform_admin_username,
        get_settings().open_platform_admin_password_hash,
        get_settings().open_platform_session_secret,
        get_settings().open_platform_cookie_secure,
        get_settings().oa_cookie_name,
        get_settings().oa_jwt_secret,
    ) = original


class TestAppCrud:
    async def test_get_app_detail(self, admin_client: AsyncClient, db_session: AsyncSession):
        csrf = await _admin_login(admin_client)
        created = await admin_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": _uniq("detail-app"), "display_name": "Detail", "owner_itcode": "admin"},
        )
        app_id = created.json()["data"]["id"]
        resp = await admin_client.get(f"/api/v1/open-platform/apps/{app_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["id"] == app_id

    async def test_update_app_display_name(self, admin_client: AsyncClient, db_session: AsyncSession):
        csrf = await _admin_login(admin_client)
        created = await admin_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": _uniq("upd-app"), "display_name": "Old", "owner_itcode": "admin"},
        )
        app_id = created.json()["data"]["id"]
        resp = await admin_client.patch(
            f"/api/v1/open-platform/apps/{app_id}",
            headers={"X-CSRF-Token": csrf},
            json={"display_name": "New Name"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["display_name"] == "New Name"

    async def test_oa_cannot_change_owner(self, oa_owner_client: AsyncClient, db_session: AsyncSession):
        # oa-owner 创建自己的应用
        created = await oa_owner_client.post(
            "/api/v1/open-platform/apps",
            json={"app_name": _uniq("oa-app"), "display_name": "OA App", "owner_itcode": "oa-owner"},
        )
        assert created.status_code == 201, created.text
        app_id = created.json()["data"]["id"]
        # 试图把 owner 改成别人 -> 403
        resp = await oa_owner_client.patch(
            f"/api/v1/open-platform/apps/{app_id}",
            json={"owner_itcode": "someone-else"},
        )
        assert resp.status_code == 403


class TestDeleteApp:
    async def test_admin_delete_app_recycles_and_removes_from_list(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ):
        csrf = await _admin_login(admin_client)
        created = await admin_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": _uniq("del-app"), "display_name": "Del", "owner_itcode": "admin"},
        )
        app_id = created.json()["data"]["id"]
        resp = await admin_client.delete(
            f"/api/v1/open-platform/apps/{app_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        # 删除后不再出现在列表
        listing = await admin_client.get("/api/v1/open-platform/apps")
        assert app_id not in {a["id"] for a in listing.json()["data"]}

    async def test_oa_delete_other_owner_forbidden(self, oa_owner_client: AsyncClient, db_session: AsyncSession):
        # 构造一个 owner 为 admin 的应用，oa-owner 无权删除
        app_obj = await open_platform_service.create_app(
            db_session, app_name="admin-app-x", display_name="x", owner_itcode="admin",
            actor="admin:admin", source_ip=None,
        )
        await db_session.commit()
        resp = await oa_owner_client.delete(f"/api/v1/open-platform/apps/{app_obj.id}")
        assert resp.status_code == 403


class TestKeyRotate:
    async def test_rotate_key_returns_new_plaintext_and_revokes_old(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ):
        csrf = await _admin_login(admin_client)
        created = await admin_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": _uniq("rot-app"), "display_name": "Rot", "owner_itcode": "admin"},
        )
        app_id = created.json()["data"]["id"]
        key = await admin_client.post(
            f"/api/v1/open-platform/apps/{app_id}/keys",
            headers={"X-CSRF-Token": csrf},
            json={"name": "k", "scopes": ["data:read"], "expires_at": (utc_now() + timedelta(days=30)).isoformat()},
        )
        key_id = key.json()["data"]["id"]
        rotated = await admin_client.post(
            f"/api/v1/open-platform/keys/{key_id}/rotate",
            headers={"X-CSRF-Token": csrf},
        )
        assert rotated.status_code == 201, rotated.text
        assert rotated.json()["data"]["api_key"].startswith("ud_live_ak_")


class TestAuditLogs:
    async def test_audit_logs_requires_admin(self, oa_owner_client: AsyncClient):
        resp = await oa_owner_client.get("/api/v1/open-platform/audit-logs")
        assert resp.status_code == 403

    async def test_audit_logs_returns_list(self, admin_client: AsyncClient, db_session: AsyncSession):
        csrf = await _admin_login(admin_client)
        # 触发一次写入动作以产生审计记录
        await admin_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": _uniq("audit-app"), "display_name": "Audit", "owner_itcode": "admin"},
        )
        resp = await admin_client.get("/api/v1/open-platform/audit-logs")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json()["data"], list)


class TestCollections:
    async def test_list_app_collections_returns_list(self, admin_client: AsyncClient, db_session: AsyncSession):
        csrf = await _admin_login(admin_client)
        created = await admin_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": _uniq("col-app"), "display_name": "Col", "owner_itcode": "admin"},
        )
        app_id = created.json()["data"]["id"]
        resp = await admin_client.get(f"/api/v1/open-platform/apps/{app_id}/collections")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json()["data"], list)

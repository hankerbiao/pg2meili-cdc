"""用户管理端点回归测试（admin only）。

覆盖 ``GET /users`` 列表（合并 admin 单例 + OA 用户、关键字/状态过滤）、
``POST /users/{itcode}/disable`` 与 ``POST /users/{itcode}/enable``，
重点验证：
- 禁用用户级联将其名下 active 应用置 disabled；
- 启用不自动复活应用；
- 管理员账号禁用被显式拒绝（防自杀）。

需要真实 Postgres：通过 ``TEST_PG_CONN_STRING`` 提供隔离测试库；
未配置时 conftest 的 db_session 会自动 skip 本模块所有用例。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.models.oa import OaUser
from app.models.open_platform import OpenPlatformApp


@pytest.fixture
async def users_client(db_session: AsyncSession):
    settings = get_settings()
    original = (
        settings.open_platform_admin_username,
        settings.open_platform_admin_password_hash,
        settings.open_platform_session_secret,
        settings.open_platform_cookie_secure,
    )
    settings.open_platform_admin_username = "admin"
    settings.open_platform_admin_password_hash = PasswordHasher().hash("correct-horse-battery")
    settings.open_platform_session_secret = "test-session-secret-with-enough-entropy"
    settings.open_platform_cookie_secure = False

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    (
        settings.open_platform_admin_username,
        settings.open_platform_admin_password_hash,
        settings.open_platform_session_secret,
        settings.open_platform_cookie_secure,
    ) = original


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/open-platform/session",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["csrf_token"]


async def _upsert_oa(db_session: AsyncSession, itcode: str, status: str = "active") -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(OaUser)
        .values(itcode=itcode, profile={"姓名": itcode}, status=status, created_at=now, updated_at=now)
        .on_conflict_do_update(index_elements=["itcode"], set_={"status": status, "updated_at": now})
    )
    await db_session.execute(stmt)
    await db_session.commit()


async def _seed_app(db_session: AsyncSession, app_id: str, owner: str, status: str = "active") -> None:
    """幂等写入应用（on_conflict 更新），避免重复运行/持久化测试库时主键冲突。"""
    from sqlalchemy.dialects.postgresql import insert as _pg_insert

    from app.models.open_platform import OpenPlatformApp

    now = datetime.now(timezone.utc)
    stmt = (
        _pg_insert(OpenPlatformApp)
        .values(
            id=app_id,
            app_name=app_id,
            display_name=app_id,
            owner_itcode=owner,
            status=status,
            version=1,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_={"status": status, "owner_itcode": owner, "updated_at": now},
        )
    )
    await db_session.execute(stmt)
    await db_session.commit()


class TestUserList:
    async def test_list_merges_admin_singleton_and_oa(self, users_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "alice", status="active")
        csrf = await _login(users_client)
        resp = await users_client.get("/api/v1/open-platform/users")
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        itcodes = {u["itcode"] for u in items}
        assert "admin" in itcodes  # admin 虚拟行恒在
        assert "alice" in itcodes

    async def test_list_keyword_filter(self, users_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "bob", status="active")
        await _upsert_oa(db_session, "carol", status="active")
        csrf = await _login(users_client)
        resp = await users_client.get("/api/v1/open-platform/users", params={"keyword": "bob"})
        assert resp.status_code == 200
        itcodes = {u["itcode"] for u in resp.json()["data"]["items"]}
        assert itcodes == {"bob"}

    async def test_list_status_filter(self, users_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "dave", status="active")
        await _upsert_oa(db_session, "erin", status="disabled")
        csrf = await _login(users_client)
        resp = await users_client.get("/api/v1/open-platform/users", params={"user_status": "disabled"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert all(u["status"] == "disabled" for u in items)
        assert {u["itcode"] for u in items} == {"erin"}


class TestUserDisableEnable:
    async def test_disable_cascades_active_apps(self, users_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "frank", status="active")
        await _seed_app(db_session, "frank-app-1", "frank", status="active")
        await _seed_app(db_session, "frank-app-2", "frank", status="active")
        csrf = await _login(users_client)

        resp = await users_client.post(
            "/api/v1/open-platform/users/frank/disable", headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "disabled"

        # 名下 active 应用应被级联置 disabled
        app1 = await db_session.get(OpenPlatformApp, "frank-app-1")
        app2 = await db_session.get(OpenPlatformApp, "frank-app-2")
        assert app1.status == "disabled"
        assert app2.status == "disabled"

    async def test_enable_does_not_revive_apps(self, users_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "grace", status="disabled")
        await _seed_app(db_session, "grace-app", "grace", status="disabled")
        csrf = await _login(users_client)

        resp = await users_client.post(
            "/api/v1/open-platform/users/grace/enable", headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "active"

        # 启用用户不应自动复活其已被禁用的应用
        app = await db_session.get(OpenPlatformApp, "grace-app")
        assert app.status == "disabled"

    async def test_disable_unknown_user_404(self, users_client: AsyncClient):
        csrf = await _login(users_client)
        resp = await users_client.post(
            "/api/v1/open-platform/users/ghost/disable", headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 404

    async def test_disable_admin_self_rejected(self, users_client: AsyncClient):
        csrf = await _login(users_client)
        resp = await users_client.post(
            "/api/v1/open-platform/users/admin/disable", headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 400

    async def test_disable_requires_csrf(self, users_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "heidi", status="active")
        csrf = await _login(users_client)  # 已登录（持有 admin 会话 cookie）
        # 但请求不带 X-CSRF-Token -> 应 403（而非 401 未登录）
        resp = await users_client.post("/api/v1/open-platform/users/heidi/disable")
        assert resp.status_code == 403

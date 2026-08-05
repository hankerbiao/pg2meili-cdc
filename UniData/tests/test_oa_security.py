"""OA 安全模型回归测试。

覆盖统一登录体系的关键安全不变量：
- 禁用用户拦截（assert_oa_user_active 单元 + /oa/me 接口）
- OA 写操作 CSRF 豁免、管理员写操作 CSRF 强制
- OA 用户应用数据隔离（owner_itcode 过滤）
- 双会话回退：管理员 cookie 失效时回退 OA，而非 401 锁死（P0-3）

需要真实 Postgres：通过环境变量 TEST_PG_CONN_STRING 提供隔离测试库；
未配置时 conftest 的 db_session fixture 会自动 skip 本模块所有用例。
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
from app.core.oa_auth import create_oa_session
from app.main import app
from app.models.oa import OaUser
from app.services.oa_service import assert_oa_user_active


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _oa_token(itcode: str, name: str = "tester") -> str:
    token, _ = create_oa_session(itcode, {"姓名": name, "email": f"{itcode}@example.com"})
    return token


def _cookie_name() -> str:
    return get_settings().oa_cookie_name


async def _upsert_oa(db_session: AsyncSession, itcode: str, status: str = "active") -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(OaUser)
        .values(itcode=itcode, profile={"姓名": itcode}, status=status, created_at=now, updated_at=now)
        .on_conflict_do_update(index_elements=["itcode"], set_={"status": status, "updated_at": now})
    )
    await db_session.execute(stmt)
    await db_session.commit()


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
async def oa_client(db_session: AsyncSession):
    """OA/管理员会话测试客户端：注入测试 DB，并以固定密钥签发会话。"""
    settings = get_settings()
    original = (
        settings.open_platform_session_secret,
        settings.open_platform_admin_username,
        settings.open_platform_admin_password_hash,
        settings.open_platform_cookie_secure,
    )
    settings.open_platform_session_secret = "test-session-secret-with-enough-entropy"
    settings.open_platform_admin_username = "admin"
    settings.open_platform_admin_password_hash = PasswordHasher().hash("correct-horse-battery")
    settings.open_platform_cookie_secure = False

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    ) as client:
        yield client
    app.dependency_overrides.clear()
    (
        settings.open_platform_session_secret,
        settings.open_platform_admin_username,
        settings.open_platform_admin_password_hash,
        settings.open_platform_cookie_secure,
    ) = original


# --------------------------------------------------------------------------- #
# 1) assert_oa_user_active 单元行为
# --------------------------------------------------------------------------- #
class TestAssertOaUserActive:
    async def test_active_allows(self, db_session: AsyncSession):
        await _upsert_oa(db_session, "alice", status="active")
        # 不应抛异常
        await assert_oa_user_active(db_session, "alice")

    async def test_disabled_blocks(self, db_session: AsyncSession):
        await _upsert_oa(db_session, "bob", status="disabled")
        with pytest.raises(Exception):
            await assert_oa_user_active(db_session, "bob")

    async def test_unknown_treated_active(self, db_session: AsyncSession):
        # 不存在的用户按 active 处理，避免误伤正常登录
        await assert_oa_user_active(db_session, "ghost")


# --------------------------------------------------------------------------- #
# 2) /oa/me 禁用拦截
# --------------------------------------------------------------------------- #
class TestOaMeDisabled:
    async def test_disabled_returns_401(self, oa_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "carol", status="disabled")
        oa_client.cookies.set(_cookie_name(), _oa_token("carol"))
        resp = await oa_client.get("/api/v1/auth/oa/me")
        assert resp.status_code == 401

    async def test_active_returns_profile(self, oa_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "dave", status="active")
        oa_client.cookies.set(_cookie_name(), _oa_token("dave"))
        resp = await oa_client.get("/api/v1/auth/oa/me")
        assert resp.status_code == 200
        assert resp.json()["data"]["itcode"] == "dave"


# --------------------------------------------------------------------------- #
# 3) CSRF 豁免（OA）vs 强制（admin）
# --------------------------------------------------------------------------- #
class TestCsrf:
    async def test_oa_write_exempt_without_csrf(self, oa_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "erin", status="active")
        oa_client.cookies.set(_cookie_name(), _oa_token("erin"))
        resp = await oa_client.post(
            "/api/v1/open-platform/apps",
            json={"app_name": "erin-app", "display_name": "Erin App", "owner_itcode": "erin"},
        )
        assert resp.status_code == 201, resp.text
        # owner 强制为本人，忽略请求体
        assert resp.json()["data"]["owner_itcode"] == "erin"

    async def test_admin_write_requires_csrf(self, oa_client: AsyncClient):
        login = await oa_client.post(
            "/api/v1/open-platform/session",
            json={"username": "admin", "password": "correct-horse-battery"},
        )
        assert login.status_code == 200
        csrf = login.json()["data"]["csrf_token"]

        denied = await oa_client.post(
            "/api/v1/open-platform/apps",
            json={"app_name": "admin-app", "display_name": "Admin App", "owner_itcode": "admin"},
        )
        assert denied.status_code == 403

        allowed = await oa_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": "admin-app2", "display_name": "Admin App2", "owner_itcode": "admin"},
        )
        assert allowed.status_code == 201, allowed.text


# --------------------------------------------------------------------------- #
# 4) OA 应用数据隔离
# --------------------------------------------------------------------------- #
class TestOwnerIsolation:
    async def test_other_oa_cannot_see_apps(self, oa_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "frank", status="active")
        await _upsert_oa(db_session, "grace", status="active")
        oa_client.cookies.set(_cookie_name(), _oa_token("frank"))
        create = await oa_client.post(
            "/api/v1/open-platform/apps",
            json={"app_name": "frank-app", "display_name": "Frank App", "owner_itcode": "frank"},
        )
        assert create.status_code == 201, create.text

        oa_client.cookies.set(_cookie_name(), _oa_token("grace"))
        listing = await oa_client.get("/api/v1/open-platform/apps")
        assert listing.status_code == 200
        names = [a["app_name"] for a in listing.json()["data"]]
        assert "frank-app" not in names


# --------------------------------------------------------------------------- #
# 5) 双会话回退（P0-3）：管理员 cookie 失效不应锁死 OA 用户
# --------------------------------------------------------------------------- #
class TestDualSessionFallback:
    async def test_invalid_admin_cookie_falls_back_to_oa(self, oa_client: AsyncClient, db_session: AsyncSession):
        await _upsert_oa(db_session, "heidi", status="active")
        # 同时携带伪造（无效）管理员 cookie + 有效 OA cookie
        oa_client.cookies.set("open_platform_session", "forged.invalid.token")
        oa_client.cookies.set(_cookie_name(), _oa_token("heidi"))
        # list_apps 使用 get_any_session：修复前应 401，修复后回退 OA 身份
        resp = await oa_client.get("/api/v1/open-platform/apps")
        assert resp.status_code == 200
        # heidi 无应用，列表为空（owner 过滤生效）
        assert resp.json()["data"] == []

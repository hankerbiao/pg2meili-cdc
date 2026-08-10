"""开放平台「调用方」端到端测试。

通过**真实 API Key**（而非 ``get_current_app`` 覆盖）走完整链路：
管理员登录 → 引导创建应用与初始密钥 → 用真实密钥驱动公共数据 API
（文档 CRUD / 索引列举 / 代理在线查询）→ 吊销密钥后拒绝访问。

依赖 conftest.db_session 提供的隔离测试库（建表 + flush 不提交，测试结束回滚）。
需要环境变量 ``TEST_PG_CONN_STRING`` 指向独立的 test 库，否则用例自动 skip。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app


ADMIN_USER = "admin"
ADMIN_PASS = "correct-horse-battery"


def _iso(days: int) -> str:
    """返回未来/过去 days 天的 ISO8601 时间戳（UTC）。"""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture
async def caller_client(db_session: AsyncSession):
    """以管理员身份登录、仅覆盖 get_db 的客户端（保留真实鉴权链路）。

    管理员 cookie 登录态与调用方的 Bearer 鉴权共存于同一客户端：
    写操作（建应用/吊销）带 X-CSRF-Token 走 cookie 会话，
    公共 API 调用带 Authorization: Bearer 走真实 Key 校验。
    """
    async def override_get_db():
        yield db_session

    settings = get_settings()
    original = (
        settings.open_platform_admin_username,
        settings.open_platform_admin_password_hash,
        settings.open_platform_session_secret,
        settings.open_platform_cookie_secure,
    )
    settings.open_platform_admin_username = ADMIN_USER
    settings.open_platform_admin_password_hash = PasswordHasher().hash(ADMIN_PASS)
    settings.open_platform_session_secret = "test-session-secret-with-enough-entropy"
    settings.open_platform_cookie_secure = False
    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login_resp = await client.post(
                "/api/v1/open-platform/session",
                json={"username": ADMIN_USER, "password": ADMIN_PASS},
            )
            assert login_resp.status_code == 200, login_resp.text
            csrf = login_resp.json()["data"]["csrf_token"]
            yield client, csrf
    finally:
        app.dependency_overrides.clear()
        (
            settings.open_platform_admin_username,
            settings.open_platform_admin_password_hash,
            settings.open_platform_session_secret,
            settings.open_platform_cookie_secure,
        ) = original


class TestCallerJourney:
    async def test_full_lifecycle_with_real_api_key(self, caller_client):
        client, csrf = caller_client

        # 1) 引导创建应用 + 两类初始密钥（数据读写 / 搜索只读）
        boot = await client.post(
            "/api/v1/open-platform/apps/bootstrap",
            headers={"X-CSRF-Token": csrf},
            json={
                "app_name": "e2e-caller",
                "display_name": "E2E Caller App",
                "owner_itcode": "pytest",
                "initial_keys": [
                    {"name": "backend-full-access", "scopes": ["data:read", "data:write", "search:read"], "expires_at": _iso(90)},
                    {"name": "search-key", "scopes": ["search:read"], "expires_at": _iso(90)},
                ],
            },
        )
        assert boot.status_code == 201, boot.text
        data = boot.json()["data"]
        data_key = next(k for k in data["keys"] if "data:write" in k["scopes"])
        search_key = next(k for k in data["keys"] if k["scopes"] == ["search:read"])
        assert data_key["api_key"].startswith("ud_live_ak_")
        assert data_key["scopes"] == ["data:read", "data:write", "search:read"]

        auth = {"Authorization": f"Bearer {data_key['api_key']}"}

        # 2) 创建/更新文档
        created = await client.post(
            "/api/v1/data/products",
            headers=auth,
            json={"id": "sku-001", "name": "Mechanical Keyboard", "price": 699},
        )
        assert created.status_code == 201, created.text
        assert created.json()["data"]["id"] == "sku-001"

        # 3) 读取文档
        got = await client.get("/api/v1/data/products/sku-001", headers=auth)
        assert got.status_code == 200, got.text
        assert got.json()["data"]["name"] == "Mechanical Keyboard"

        # 4) 列表（分页默认 20）
        listed = await client.get("/api/v1/data/products", headers=auth)
        assert listed.status_code == 200
        assert any(d["id"] == "sku-001" for d in listed.json()["data"])

        # 5) 批量写入
        batched = await client.post(
            "/api/v1/data/products/batch",
            headers=auth,
            json={"items": [
                {"id": "sku-002", "name": "Mouse", "price": 199},
                {"id": "sku-003", "name": "Monitor", "price": 1299},
            ]},
        )
        assert batched.status_code == 201, batched.text
        assert batched.json()["data"]["count"] == 2

        # 6) 索引列举（应含写入过的集合）
        indexes = await client.get("/api/v1/indexes", headers=auth)
        assert indexes.status_code == 200
        assert "products" in indexes.json()["data"]

        # 7) 后端完整访问密钥也可查询在线代理（包含 search:read 权限）
        agents = await client.get("/api/v1/agents/online", headers=auth)
        assert agents.status_code == 200
        assert isinstance(agents.json()["data"], list)

        # 8) 前端搜索只读密钥可查询代理，但不能写入文档。
        search_auth = {"Authorization": f"Bearer {search_key['api_key']}"}
        frontend_agents = await client.get("/api/v1/agents/online", headers=search_auth)
        assert frontend_agents.status_code == 200
        forbidden_write = await client.post(
            "/api/v1/data/products",
            headers=search_auth,
            json={"id": "frontend-write"},
        )
        assert forbidden_write.status_code == 403

        # 9) 软删除文档后不可见
        deleted = await client.delete("/api/v1/data/products/sku-001", headers=auth)
        assert deleted.status_code == 200, deleted.text
        gone = await client.get("/api/v1/data/products/sku-001", headers=auth)
        assert gone.status_code == 404

        # 10) 吊销数据密钥后，原 Bearer 访问被拒（401）
        revoke = await client.post(
            f"/api/v1/open-platform/keys/{data_key['id']}/revoke",
            headers={"X-CSRF-Token": csrf},
        )
        assert revoke.status_code == 200, revoke.text
        denied = await client.get("/api/v1/data/products/sku-002", headers=auth)
        assert denied.status_code == 401

    async def test_scope_enforcement_write_requires_data_write(self, caller_client):
        client, csrf = caller_client

        boot = await client.post(
            "/api/v1/open-platform/apps/bootstrap",
            headers={"X-CSRF-Token": csrf},
            json={
                "app_name": "e2e-scope",
                "display_name": "E2E Scope App",
                "owner_itcode": "pytest",
                "initial_keys": [
                    {"name": "readonly", "scopes": ["data:read"], "expires_at": _iso(90)},
                ],
            },
        )
        assert boot.status_code == 201, boot.text
        read_key = boot.json()["data"]["keys"][0]["api_key"]
        auth = {"Authorization": f"Bearer {read_key}"}

        # 只读密钥允许读取
        ok_read = await client.get("/api/v1/data/products", headers=auth)
        assert ok_read.status_code == 200

        # 但写入被拒（403 权限不足）
        forbidden = await client.post(
            "/api/v1/data/products",
            headers=auth,
            json={"id": "x", "name": "n"},
        )
        assert forbidden.status_code == 403

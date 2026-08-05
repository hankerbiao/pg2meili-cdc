"""API Key 鉴权拒绝路径矩阵。

使用**真实密钥**（``ud_live_...``）验证 ``get_current_app`` 的各拒绝分支：
缺头 / 格式错 / 密钥错 / 过期 / 吊销 / 应用禁用 / 权限不足 / X-App-Name 不匹配，
以及合法密钥放行的正向用例。

仅在测试库内 flush 不提交，保证用例间隔离（不污染共享测试库）。
需要环境变量 ``TEST_PG_CONN_STRING`` 指向独立的 test 库，否则用例自动 skip。
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.models import OpenPlatformApp
from app.services.open_platform_service import open_platform_service, utc_now


# 受保护目标：文档列表（需 data:read）；写入目标（需 data:write）
READ_TARGET = "/api/v1/data/products"
WRITE_TARGET = "/api/v1/data/products"


@pytest.fixture
async def key_client(db_session: AsyncSession):
    """仅覆盖 get_db，使用真实 API Key 鉴权（不覆盖 get_current_app）。"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def issue_key(db_session: AsyncSession):
    """在 test-app-id 下签发真实密钥，支持注入过期/吊销等状态（仅 flush 不提交）。"""
    async def _issue(scopes=("data:read", "data:write"), days: int = 90, mutate=None):
        key, plaintext = await open_platform_service.create_key(
            db_session,
            app_id="test-app-id",
            name="auth-test-key",
            scopes=list(scopes),
            expires_at=utc_now() + timedelta(days=days),
            actor="test",
            source_ip=None,
        )
        if mutate is not None:
            mutate(key)
            await db_session.flush()
        return plaintext
    return _issue


class TestApiKeyAuthRejections:
    async def test_missing_authorization_header(self, key_client):
        resp = await key_client.get(READ_TARGET)
        assert resp.status_code == 401

    async def test_malformed_authorization_value(self, key_client):
        resp = await key_client.get(
            READ_TARGET,
            headers={"Authorization": "not-a-bearer-token"},
        )
        assert resp.status_code == 401

    async def test_wrong_secret_for_existing_key(self, key_client, issue_key):
        plaintext = await issue_key(scopes=("data:read",))
        key_id = plaintext.split(".", 1)[0].replace("ud_live_", "")
        # 伪造同 key_id 但 secret 错误的令牌（secret 需 >=40 字符以通过格式校验）
        forged = f"ud_live_{key_id}.wrongsecretwrongsecretwrongsecretwrongsecret"
        resp = await key_client.get(
            READ_TARGET,
            headers={"Authorization": f"Bearer {forged}"},
        )
        assert resp.status_code == 401

    async def test_expired_key(self, key_client, issue_key):
        plaintext = await issue_key(
            mutate=lambda k: setattr(k, "expires_at", utc_now() - timedelta(days=1)),
        )
        resp = await key_client.get(
            READ_TARGET,
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 401

    async def test_revoked_key(self, key_client, issue_key):
        plaintext = await issue_key(
            mutate=lambda k: setattr(k, "status", "revoked"),
        )
        resp = await key_client.get(
            READ_TARGET,
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 401

    async def test_disabled_app(self, key_client, issue_key, db_session: AsyncSession):
        app_row = await db_session.get(OpenPlatformApp, "test-app-id")
        plaintext = await issue_key()
        app_row.status = "disabled"
        await db_session.flush()
        resp = await key_client.get(
            READ_TARGET,
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 401

    async def test_x_app_name_mismatch(self, key_client, issue_key):
        plaintext = await issue_key()
        resp = await key_client.get(
            READ_TARGET,
            headers={"Authorization": f"Bearer {plaintext}", "X-App-Name": "other-app"},
        )
        assert resp.status_code == 401

    async def test_scope_missing_returns_403(self, key_client, issue_key):
        plaintext = await issue_key(scopes=("data:read",))
        auth = {"Authorization": f"Bearer {plaintext}"}

        ok_read = await key_client.get(READ_TARGET, headers=auth)
        assert ok_read.status_code == 200

        forbidden = await key_client.post(
            WRITE_TARGET,
            headers=auth,
            json={"id": "z", "name": "n"},
        )
        assert forbidden.status_code == 403

    async def test_valid_key_succeeds(self, key_client, issue_key):
        plaintext = await issue_key(scopes=("data:read", "data:write"))
        resp = await key_client.get(
            READ_TARGET,
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 200


class TestApiKeyFormat:
    async def test_plaintext_only_returned_on_creation(self, db_session: AsyncSession):
        """密钥明文仅在创建时一次性返回，列表/详情接口不回显。"""
        from httpx import ASGITransport, AsyncClient

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                from argon2 import PasswordHasher
                from app.core.config import get_settings

                settings = get_settings()
                orig = (
                    settings.open_platform_admin_username,
                    settings.open_platform_admin_password_hash,
                    settings.open_platform_session_secret,
                    settings.open_platform_cookie_secure,
                )
                settings.open_platform_admin_username = "admin"
                settings.open_platform_admin_password_hash = PasswordHasher().hash("correct-horse-battery")
                settings.open_platform_session_secret = "test-session-secret-with-enough-entropy"
                settings.open_platform_cookie_secure = False

                login = await client.post(
                    "/api/v1/open-platform/session",
                    json={"username": "admin", "password": "correct-horse-battery"},
                )
                csrf = login.json()["data"]["csrf_token"]
                created = await client.post(
                    "/api/v1/open-platform/apps",
                    headers={"X-CSRF-Token": csrf},
                    json={"app_name": "fmt-app", "display_name": "Fmt", "owner_itcode": "pytest"},
                )
                app_id = created.json()["data"]["id"]
                key = await client.post(
                    f"/api/v1/open-platform/apps/{app_id}/keys",
                    headers={"X-CSRF-Token": csrf},
                    json={"name": "k", "scopes": ["data:read"], "expires_at": (utc_now() + timedelta(days=30)).isoformat()},
                )
                assert key.status_code == 201
                assert "api_key" in key.json()["data"]

                listed = await client.get(f"/api/v1/open-platform/apps/{app_id}/keys")
                assert "api_key" not in listed.json()["data"][0]
                (
                    settings.open_platform_admin_username,
                    settings.open_platform_admin_password_hash,
                    settings.open_platform_session_secret,
                    settings.open_platform_cookie_secure,
                ) = orig
        finally:
            app.dependency_overrides.clear()

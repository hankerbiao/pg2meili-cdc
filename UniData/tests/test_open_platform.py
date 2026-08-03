from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app


@pytest.fixture
async def platform_client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

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


async def login(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/open-platform/session",
        json={"username": "admin", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["csrf_token"]


class TestOpenPlatform:
    async def test_admin_session_requires_csrf(self, platform_client: AsyncClient):
        csrf = await login(platform_client)
        denied = await platform_client.post(
            "/api/v1/open-platform/apps",
            json={"app_name": "orders", "display_name": "Orders", "owner_itcode": "owner"},
        )
        assert denied.status_code == 403
        allowed = await platform_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": "orders", "display_name": "Orders", "owner_itcode": "owner"},
        )
        assert allowed.status_code == 201

    async def test_bootstrap_app_creates_initial_key_atomically(self, platform_client: AsyncClient):
        csrf = await login(platform_client)
        response = await platform_client.post(
            "/api/v1/open-platform/apps/bootstrap",
            headers={"X-CSRF-Token": csrf},
            json={
                "app_name": "bootstrap-app",
                "display_name": "Bootstrap App",
                "owner_itcode": "owner",
                "initial_keys": [
                    {
                        "name": "frontend-search",
                        "scopes": ["search:read"],
                        "expires_at": (
                            datetime.now(timezone.utc) + timedelta(days=90)
                        ).isoformat(),
                    },
                    {
                        "name": "backend-data",
                        "scopes": ["data:read", "data:write"],
                        "expires_at": (
                            datetime.now(timezone.utc) + timedelta(days=90)
                        ).isoformat(),
                    },
                ],
            },
        )

        assert response.status_code == 201, response.text
        result = response.json()["data"]
        assert result["app"]["app_name"] == "bootstrap-app"
        assert [key["name"] for key in result["keys"]] == [
            "frontend-search",
            "backend-data",
        ]
        assert result["keys"][0]["scopes"] == ["search:read"]
        assert result["keys"][1]["scopes"] == ["data:read", "data:write"]
        assert all(key["api_key"].startswith("ud_live_ak_") for key in result["keys"])

        listed = await platform_client.get(
            f"/api/v1/open-platform/apps/{result['app']['id']}/keys"
        )
        assert listed.status_code == 200
        assert {key["name"] for key in listed.json()["data"]} == {
            "frontend-search",
            "backend-data",
        }
        assert all("api_key" not in key for key in listed.json()["data"])

    async def test_key_plaintext_is_returned_once_and_legacy_jwt_is_rejected(self, platform_client: AsyncClient):
        csrf = await login(platform_client)
        app_response = await platform_client.post(
            "/api/v1/open-platform/apps",
            headers={"X-CSRF-Token": csrf},
            json={"app_name": "catalog", "display_name": "Catalog", "owner_itcode": "owner"},
        )
        app_id = app_response.json()["data"]["id"]
        key_response = await platform_client.post(
            f"/api/v1/open-platform/apps/{app_id}/keys",
            headers={"X-CSRF-Token": csrf},
            json={
                "name": "production",
                "scopes": ["search:read", "data:read"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            },
        )
        assert key_response.status_code == 201, key_response.text
        api_key = key_response.json()["data"]["api_key"]
        assert api_key.startswith("ud_live_ak_")

        listed = await platform_client.get(f"/api/v1/open-platform/apps/{app_id}/keys")
        assert "api_key" not in listed.json()["data"][0]

        legacy = await platform_client.get(
            "/api/v1/agents/online",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"},
        )
        assert legacy.status_code == 401

        accepted = await platform_client.get(
            "/api/v1/agents/online",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert accepted.status_code == 200

        key_id = key_response.json()["data"]["id"]
        revoked = await platform_client.post(
            f"/api/v1/open-platform/keys/{key_id}/revoke",
            headers={"X-CSRF-Token": csrf},
        )
        assert revoked.status_code == 200
        rejected = await platform_client.get(
            "/api/v1/agents/online",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert rejected.status_code == 401

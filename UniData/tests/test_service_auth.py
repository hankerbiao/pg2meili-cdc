from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.credentials import decrypt_secret, encrypt_secret
from app.core.service_auth import (
    SERVICE_SCOPE_APPS_WRITE,
    SERVICE_SCOPE_COLLECTIONS_WRITE,
    consume_refresh_token,
    get_service_identity,
    issue_access_token,
    issue_refresh_token,
    verify_client_credentials,
)


def _settings_snapshot():
    settings = get_settings()
    fields = (
        "open_platform_session_secret",
        "open_platform_service_jwt_secret",
        "open_platform_service_jwt_issuer",
        "open_platform_service_jwt_audience",
        "open_platform_service_client_id",
        "open_platform_service_client_secret",
        "open_platform_service_access_ttl_seconds",
        "open_platform_service_scopes",
        "open_platform_credential_encryption_key",
    )
    return settings, {field: getattr(settings, field) for field in fields}


def test_access_token_contains_management_claims():
    settings, original = _settings_snapshot()
    settings.open_platform_session_secret = "session-secret-with-at-least-32-characters"
    settings.open_platform_service_jwt_secret = "jwt-secret-with-at-least-32-characters"
    settings.open_platform_service_jwt_issuer = "melidata"
    settings.open_platform_service_jwt_audience = "melidata-management"
    settings.open_platform_service_client_id = "apps"
    settings.open_platform_service_access_ttl_seconds = 600
    try:
        token, expires_in = issue_access_token(
            "apps",
            [SERVICE_SCOPE_APPS_WRITE, SERVICE_SCOPE_COLLECTIONS_WRITE],
        )
        assert expires_in == 600
        claims = jwt.decode(
            token,
            settings.open_platform_service_jwt_secret,
            algorithms=["HS256"],
            audience="melidata-management",
            issuer="melidata",
        )
        assert claims["sub"] == "apps"
        assert claims["aud"] == "melidata-management"
        assert claims["scope"] == "open-platform:apps:write open-platform:collections:write"
        assert claims["typ"] == "access"
        assert claims["exp"] - claims["iat"] == 600
    finally:
        for field, value in original.items():
            setattr(settings, field, value)


def test_client_credentials_reject_unknown_secret():
    settings, original = _settings_snapshot()
    settings.open_platform_service_client_id = "apps"
    settings.open_platform_service_client_secret = "client-secret"
    try:
        with pytest.raises(HTTPException) as exc_info:
            verify_client_credentials("apps", "wrong")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "invalid_client"
    finally:
        for field, value in original.items():
            setattr(settings, field, value)


@pytest.mark.asyncio
async def test_refresh_token_is_one_time_and_keeps_scope():
    settings, original = _settings_snapshot()
    settings.open_platform_service_refresh_ttl_seconds = 86400

    class FakeDB:
        def __init__(self):
            self.added = []
            self.token = None

        def add(self, value):
            self.added.append(value)
            self.token = value

        async def scalar(self, _query):
            return self.token

    db = FakeDB()
    try:
        raw, expires_in = issue_refresh_token(db, "apps", [SERVICE_SCOPE_APPS_WRITE])
        assert expires_in == 86400
        assert db.token.scopes == [SERVICE_SCOPE_APPS_WRITE]
        scopes = await consume_refresh_token(db, raw, "apps")
        assert scopes == frozenset({SERVICE_SCOPE_APPS_WRITE})
        with pytest.raises(HTTPException) as exc_info:
            await consume_refresh_token(db, raw, "apps")
        assert exc_info.value.detail == "invalid_grant"
    finally:
        for field, value in original.items():
            setattr(settings, field, value)


@pytest.mark.asyncio
async def test_service_identity_rejects_wrong_audience():
    settings, original = _settings_snapshot()
    settings.open_platform_session_secret = "session-secret-with-at-least-32-characters"
    settings.open_platform_service_jwt_secret = "jwt-secret-with-at-least-32-characters"
    settings.open_platform_service_jwt_issuer = "melidata"
    settings.open_platform_service_jwt_audience = "melidata-management"
    settings.open_platform_service_client_id = "apps"
    try:
        token = jwt.encode(
            {
                "iss": "melidata",
                "sub": "apps",
                "aud": "other-audience",
                "scope": SERVICE_SCOPE_APPS_WRITE,
                "iat": 1,
                "exp": int(datetime.now(timezone.utc).timestamp()) + 600,
                "typ": "access",
            },
            settings.open_platform_service_jwt_secret,
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_service_identity(f"Bearer {token}")
        assert exc_info.value.status_code == 401
    finally:
        for field, value in original.items():
            setattr(settings, field, value)


def test_credential_encryption_round_trip_does_not_store_plaintext():
    settings, original = _settings_snapshot()
    settings.open_platform_session_secret = "session-secret-with-at-least-32-characters"
    settings.open_platform_credential_encryption_key = base64.urlsafe_b64encode(
        hashlib.sha256(b"test-key").digest()
    ).decode()
    plaintext = "ud_live_ak_0123456789abcdef.secret-value"
    try:
        ciphertext, nonce = encrypt_secret(plaintext)
        assert plaintext not in ciphertext
        assert decrypt_secret(ciphertext, nonce) == plaintext
    finally:
        for field, value in original.items():
            setattr(settings, field, value)

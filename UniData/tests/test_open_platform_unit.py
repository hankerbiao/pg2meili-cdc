import hashlib

import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException

from app.core.admin_auth import create_admin_session, decode_admin_session, verify_admin_password
from app.core.auth import parse_api_key
from app.core.config import get_settings
from app.services.open_platform_service import generate_api_key


def test_api_key_format_and_digest_do_not_store_plaintext():
    key_id, plaintext, digest = generate_api_key()
    parsed = parse_api_key(plaintext)
    assert parsed is not None
    assert parsed[0] == key_id
    assert hashlib.sha256(parsed[1].encode()).hexdigest() == digest
    assert plaintext not in digest


def test_legacy_jwt_is_not_an_api_key():
    assert parse_api_key("eyJhbGciOiJIUzI1NiJ9.payload.signature") is None


def test_admin_session_detects_tampering():
    settings = get_settings()
    original = (
        settings.open_platform_admin_username,
        settings.open_platform_admin_password_hash,
        settings.open_platform_session_secret,
    )
    settings.open_platform_admin_username = "admin"
    settings.open_platform_admin_password_hash = PasswordHasher().hash("correct-horse-battery")
    settings.open_platform_session_secret = "test-session-secret-with-enough-entropy"
    try:
        assert verify_admin_password("admin", "correct-horse-battery")
        assert not verify_admin_password("admin", "wrong-password")
        token, session = create_admin_session("admin")
        assert decode_admin_session(token) == session
        with pytest.raises(HTTPException):
            decode_admin_session(token[:-1] + ("A" if token[-1] != "A" else "B"))
    finally:
        (
            settings.open_platform_admin_username,
            settings.open_platform_admin_password_hash,
            settings.open_platform_session_secret,
        ) = original

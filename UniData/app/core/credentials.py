"""Application-layer encryption for one-time API key custody."""
from __future__ import annotations

import base64
import binascii
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


def _encryption_key() -> bytes:
    settings = get_settings()
    raw = settings.open_platform_credential_encryption_key.strip()
    if not raw:
        # Backwards-compatible local development fallback. Production must
        # provide a dedicated key via OPEN_PLATFORM_CREDENTIAL_ENCRYPTION_KEY_FILE.
        raw = settings.open_platform_session_secret.strip()
    if not raw:
        raise RuntimeError("OPEN_PLATFORM_CREDENTIAL_ENCRYPTION_KEY 未配置")
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (ValueError, binascii.Error):
        decoded = b""
    if len(decoded) not in (16, 24, 32):
        decoded = hashlib.sha256(raw.encode("utf-8")).digest()
    return decoded


def encrypt_secret(plaintext: str) -> tuple[str, str]:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(ciphertext).decode("ascii"), base64.urlsafe_b64encode(nonce).decode("ascii")


def decrypt_secret(ciphertext: str, nonce: str) -> str:
    value = AESGCM(_encryption_key()).decrypt(
        base64.urlsafe_b64decode(nonce),
        base64.urlsafe_b64decode(ciphertext),
        None,
    )
    return value.decode("utf-8")

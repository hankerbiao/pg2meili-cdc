"""开放平台管理员登录、签名会话与 CSRF 校验。"""
from __future__ import annotations

from app.core.encoding import b64encode as _b64encode, b64decode as _b64decode
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import get_settings


SESSION_COOKIE = "open_platform_session"
SESSION_SECRET_MIN_LENGTH = 32


@dataclass(frozen=True)
class AdminSession:
    username: str
    csrf_token: str
    expires_at: int


# _b64encode / _b64decode 见 app.core.encoding（与 oa_auth 共用）


def get_session_secret() -> str:
    settings = get_settings()
    secret = settings.open_platform_session_secret.strip()
    if len(secret) < SESSION_SECRET_MIN_LENGTH:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="开放平台会话密钥未配置或过短")
    return secret


def verify_admin_password(username: str, password: str) -> bool:
    settings = get_settings()
    encoded = settings.open_platform_admin_password_hash.strip()
    get_session_secret()
    if not encoded:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="开放平台管理员未配置")
    if not secrets.compare_digest(username, settings.open_platform_admin_username):
        return False
    try:
        return PasswordHasher().verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_admin_session(username: str) -> tuple[str, AdminSession]:
    settings = get_settings()
    secret = get_session_secret()
    now = int(time.time())
    session = AdminSession(
        username=username,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=now + settings.open_platform_session_ttl_seconds,
    )
    payload = _b64encode(json.dumps({"u": username, "c": session.csrf_token, "e": session.expires_at}, separators=(",", ":")).encode())
    signature = _b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}", session


def decode_admin_session(token: str) -> AdminSession:
    settings = get_settings()
    secret = get_session_secret()
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        decoded = json.loads(_b64decode(payload))
        session = AdminSession(username=str(decoded["u"]), csrf_token=str(decoded["c"]), expires_at=int(decoded["e"]))
        if session.expires_at <= int(time.time()):
            raise ValueError
        return session
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员会话无效或已过期")


def get_admin_session(request: Request) -> AdminSession:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录开放平台")
    return decode_admin_session(token)


def require_admin_csrf(
    session: AdminSession = Depends(get_admin_session),
    csrf_token: str = Header(default="", alias="X-CSRF-Token"),
) -> AdminSession:
    if not csrf_token or not hmac.compare_digest(csrf_token, session.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
    return session

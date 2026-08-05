"""OA 单点登录（springboard）验签与无状态会话。

设计：复用开放平台管理员的 HMAC 签名 cookie 模式（app/core/admin_auth.py），
OA 普通用户会话为无状态签名 cookie，与管理员会话相互独立、互不干扰。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

# OA 回调 JWT 允许的时钟偏差（秒）。吸收 springboard 与本网服务时钟的微小不一致，
# 避免 token 在有效期边缘被误判为"已过期"而把用户弹回登录页（302 -> ?oa=error）。
OA_JWT_EXP_LEEWAY_SECONDS = 60


@dataclass(frozen=True)
class OaSession:
    itcode: str
    name: str
    email: str
    expires_at: int


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def decode_and_verify_oa_jwt(token: str, secret: str) -> dict:
    """验签 springboard 回调的 HS256 JWT（payload 即加密的登录信息）。

    返回解码后的 payload dict；任何格式 / 验签 / 过期问题均抛出 400 HTTPException。
    """
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录信息格式错误")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        sig_bytes = _base64url_decode(signature_b64)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录信息签名编码错误")
    if not hmac.compare_digest(expected_sig, sig_bytes):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录信息验签失败")
    try:
        payload = json.loads(_base64url_decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录信息解析失败")
    exp = payload.get("exp")
    if exp is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录信息缺少过期时间")
    if time.time() > float(exp) + OA_JWT_EXP_LEEWAY_SECONDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OA 登录信息已过期")
    return payload


def _profile_name(profile: dict) -> str:
    return str(profile.get("姓名") or profile.get("name") or profile.get("displayName") or profile.get("itcode") or "")


def _profile_email(profile: dict) -> str:
    return str(profile.get("email") or profile.get("邮箱") or "")


def create_oa_session(itcode: str, profile: dict) -> tuple[str, OaSession]:
    """生成 OA 会话签名 token 与 OaSession 元信息。"""
    settings = get_settings()
    now = int(time.time())
    session = OaSession(
        itcode=itcode,
        name=_profile_name(profile),
        email=_profile_email(profile),
        expires_at=now + settings.oa_session_ttl_seconds,
    )
    payload = _b64encode(
        json.dumps(
            {"u": session.itcode, "n": session.name, "e": session.email, "x": session.expires_at},
            separators=(",", ":"),
        ).encode()
    )
    signature = _b64encode(
        hmac.new(settings.open_platform_session_secret.encode(), payload.encode(), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}", session


def decode_oa_session(token: str) -> OaSession:
    """校验 OA 会话 token（HMAC + 过期），失败抛 401。"""
    settings = get_settings()
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(
            hmac.new(settings.open_platform_session_secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        decoded = json.loads(_b64decode(payload))
        session = OaSession(
            itcode=str(decoded["u"]),
            name=str(decoded.get("n", "")),
            email=str(decoded.get("e", "")),
            expires_at=int(decoded["x"]),
        )
        if session.expires_at <= int(time.time()):
            raise ValueError
        return session
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OA 会话无效或已过期")


def get_oa_user(request: Request) -> OaSession:
    """依赖注入：从 cookie 读取并校验 OA 会话，无效则 401。"""
    settings = get_settings()
    token = request.cookies.get(settings.oa_cookie_name, "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先通过 OA 登录")
    return decode_oa_session(token)

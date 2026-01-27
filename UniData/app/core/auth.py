"""应用身份校验模块（基于 JWT）。"""
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import List, Optional

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


@dataclass
class AppIdentity:
    app_name: str
    scopes: List[str]


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _decode_jwt(token: str, secret: str, algorithms: Optional[List[str]] = None) -> dict:
    if algorithms is None:
        algorithms = ["HS256"]

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌格式",
        )

    header_b64, payload_b64, signature_b64 = parts

    try:
        header = json.loads(_base64url_decode(header_b64))
        payload = json.loads(_base64url_decode(payload_b64))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法解析令牌",
        )

    alg = header.get("alg")
    if alg not in algorithms:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不支持的签名算法",
        )

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")

    if not hmac.compare_digest(expected_sig_b64, signature_b64):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌签名无效",
        )

    exp = payload.get("exp")
    if exp is not None:
        try:
            exp_int = int(exp)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌过期时间无效",
            )
        now = int(time.time())
        if now >= exp_int:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已过期",
            )

    return payload


async def get_current_app(
    authorization: str = Header(default="", alias="Authorization"),
    x_app_name: str = Header(default="", alias="X-App-Name"),
) -> AppIdentity:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization 头",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Authorization 格式",
        )

    settings = get_settings()
    secret = settings.jwt_secret

    payload = _decode_jwt(token, secret=secret, algorithms=["HS256"])

    app_name = payload.get("app_name") or payload.get("sub")
    if not app_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少 app_name",
        )

    if x_app_name and x_app_name != app_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌与头部应用名称不匹配",
        )

    scopes_raw = payload.get("scopes") or payload.get("scope") or []
    if isinstance(scopes_raw, str):
        scopes = [s for s in scopes_raw.split() if s]
    elif isinstance(scopes_raw, list):
        scopes = [str(s) for s in scopes_raw]
    else:
        scopes = []

    return AppIdentity(app_name=app_name, scopes=scopes)

"""应用身份校验模块（基于 JWT）。

1. 从 HTTP 请求头中提取并解析 JWT；
2. 使用配置中的 jwt_secret 对令牌进行 HS256 验签与过期检查；
3. 从令牌中解析出 app_name 和 scopes，封装为 AppIdentity 返回给业务层。
"""

import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import jwt
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.services.token_revocation_service import token_revocation_service


@dataclass
class AppIdentity:
    app_name: str
    scopes: List[str]
    jti: str


def require_scopes(current_app: AppIdentity, required_scopes: List[str]) -> None:
    """确保当前 Token 具备所需权限。"""
    if not required_scopes:
        return
    missing = [scope for scope in required_scopes if scope not in current_app.scopes]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"缺少权限: {', '.join(missing)}",
        )


def generate_jwt(app_name: str, scopes: List[str], ttl_seconds: int, jti: str | None = None) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "app_name": app_name,
        "scopes": scopes,
        "exp": now + ttl_seconds,
        "iat": now,
        "jti": jti or str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_jwt(token: str, secret: str, algorithms: Optional[List[str]] = None) -> dict:
    """解析并验证 JWT，将 PyJWT 异常统一转换为 FastAPI HTTPException。"""
    if algorithms is None:
        algorithms = ["HS256"]

    try:
        return jwt.decode(token, secret, algorithms=algorithms, options={"require": ["exp", "jti"]})
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌已过期")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌")


async def get_current_app(
    authorization: str = Header(default="", alias="Authorization"),
    x_app_name: str = Header(default="", alias="X-App-Name"),
) -> AppIdentity:
    """从请求头中解析出当前调用方的应用身份。

    预期的请求头格式：
    - Authorization: Bearer <jwt>
    - X-App-Name: 可选，额外声明应用名，用于与 JWT 内容做一次交叉校验
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Authorization 头",
        )

    # 只接受标准 Bearer 令牌格式
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Authorization 格式",
        )

    settings = get_settings()
    secret = settings.jwt_secret

    payload = _decode_jwt(token, secret=secret, algorithms=["HS256"])

    # 从 payload 中提取应用名称
    app_name = payload.get("app_name") or payload.get("sub")
    if not app_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少 app_name",
        )

    # 如客户端额外传入 X-App-Name，则要求与 JWT 内部信息一致
    if x_app_name and x_app_name != app_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌与头部应用名称不匹配",
        )

    # scopes 可以是字符串（空格分隔）或列表，这里统一归一化为 List[str]
    scopes_raw = payload.get("scopes") or payload.get("scope") or []
    if isinstance(scopes_raw, str):
        scopes = [s for s in scopes_raw.split() if s]
    elif isinstance(scopes_raw, list):
        scopes = [str(s) for s in scopes_raw]
    else:
        scopes = []

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少 jti",
        )

    return AppIdentity(app_name=app_name, scopes=scopes, jti=jti)


async def get_current_app_with_revocation(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default="", alias="Authorization"),
    x_app_name: str = Header(default="", alias="X-App-Name"),
) -> AppIdentity:
    identity = await get_current_app(authorization=authorization, x_app_name=x_app_name)
    if await token_revocation_service.is_revoked(db, identity.jti):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="令牌已被撤销",
        )
    return identity

"""Service-to-service JWT and refresh-token authentication."""
from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.any_auth import AnySession, get_any_session
from app.core.config import get_settings
from app.core.database import get_db
from app.models.open_platform import ServiceRefreshToken

SERVICE_SCOPE_APPS_WRITE = "open-platform:apps:write"
SERVICE_SCOPE_COLLECTIONS_WRITE = "open-platform:collections:write"


@dataclass(frozen=True)
class ServiceIdentity:
    client_id: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class ManagementIdentity:
    role: str
    username: str
    csrf_token: str | None = None
    service: ServiceIdentity | None = None

    @property
    def is_service(self) -> bool:
        return self.service is not None

    @property
    def client_id(self) -> str | None:
        return self.service.client_id if self.service is not None else None

    @property
    def scopes(self) -> frozenset[str]:
        return self.service.scopes if self.service is not None else frozenset()


def _jwt_secret() -> str:
    settings = get_settings()
    secret = settings.open_platform_service_jwt_secret.strip()
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="服务 JWT 签名密钥未配置或过短")
    return secret


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_client_credentials(client_id: str, client_secret: str) -> None:
    settings = get_settings()
    if (
        not secrets.compare_digest(client_id, settings.open_platform_service_client_id.strip())
        or not settings.open_platform_service_client_secret.strip()
        or not secrets.compare_digest(client_secret, settings.open_platform_service_client_secret.strip())
    ):
        raise HTTPException(status_code=401, detail="invalid_client")


def issue_access_token(client_id: str, scopes: Iterable[str]) -> tuple[str, int]:
    settings = get_settings()
    expires_in = max(60, settings.open_platform_service_access_ttl_seconds)
    now = int(time.time())
    payload = {
        "iss": settings.open_platform_service_jwt_issuer,
        "sub": client_id,
        "aud": settings.open_platform_service_jwt_audience,
        "scope": " ".join(sorted(set(scopes))),
        "iat": now,
        "exp": now + expires_in,
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256"), expires_in


def issue_refresh_token(
    db: AsyncSession,
    client_id: str,
    scopes: Iterable[str],
) -> tuple[str, int]:
    settings = get_settings()
    expires_in = max(300, settings.open_platform_service_refresh_ttl_seconds)
    raw = secrets.token_urlsafe(48)
    db.add(
        ServiceRefreshToken(
            token_id=uuid.uuid4().hex,
            client_id=client_id,
            token_hash=_hash_token(raw),
            scopes=list(dict.fromkeys(scopes)),
            expires_at=datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc),
        )
    )
    return raw, expires_in


async def consume_refresh_token(
    db: AsyncSession,
    raw: str,
    client_id: str,
) -> frozenset[str]:
    token = await db.scalar(
        select(ServiceRefreshToken)
        .where(
            ServiceRefreshToken.token_hash == _hash_token(raw),
            ServiceRefreshToken.client_id == client_id,
        )
        .with_for_update()
    )
    if token is None or token.consumed_at is not None or token.revoked_at is not None:
        raise HTTPException(status_code=401, detail="invalid_grant")
    expiry = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if expiry <= _now():
        raise HTTPException(status_code=401, detail="invalid_grant")
    token.consumed_at = _now()
    return frozenset(token.scopes or [])


async def get_service_identity(
    authorization: str = Header(default="", alias="Authorization"),
) -> ManagementIdentity:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="需要服务 Bearer token")
    settings = get_settings()
    try:
        payload = jwt.decode(
            token.strip(),
            _jwt_secret(),
            algorithms=["HS256"],
            audience=settings.open_platform_service_jwt_audience,
            issuer=settings.open_platform_service_jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="服务令牌无效或已过期") from exc
    if (
        payload.get("typ") != "access"
        or not isinstance(payload.get("sub"), str)
        or payload["sub"] != settings.open_platform_service_client_id.strip()
    ):
        raise HTTPException(status_code=401, detail="服务令牌无效")
    return ManagementIdentity(
        role="service",
        username=payload["sub"],
        service=ServiceIdentity(
            client_id=payload["sub"],
            scopes=frozenset(str(payload.get("scope", "")).split()),
        ),
    )


async def require_management_auth(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default="", alias="Authorization"),
    csrf_token: str = Header(default="", alias="X-CSRF-Token"),
) -> ManagementIdentity:
    """Accept a service JWT or the existing browser session/CSRF pair."""
    if authorization.strip():
        return await get_service_identity(authorization)
    session: AnySession = await get_any_session(request, db)
    if session.role == "admin":
        expected = session.csrf_token or ""
        if not csrf_token or not secrets.compare_digest(csrf_token, expected):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
    return ManagementIdentity(
        role=session.role,
        username=session.username,
        csrf_token=session.csrf_token,
    )


def require_service_scope(identity: ManagementIdentity, scope: str) -> None:
    # Scope enforcement for the configured APPS client is intentionally
    # explicit; future clients can carry scopes in their JWT claims.
    if not identity.is_service:
        return
    if scope not in identity.scopes:
        raise HTTPException(status_code=403, detail="服务令牌缺少管理权限")

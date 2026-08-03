"""基于开放平台 API Key 的应用身份校验。"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.open_platform import ApiKey, OpenPlatformApp


API_KEY_PATTERN = re.compile(r"^ud_live_(ak_[0-9a-f]{16})\.([A-Za-z0-9_-]{40,64})$")


@dataclass
class AppIdentity:
    app_id: str
    app_name: str
    scopes: List[str]
    key_id: str


def require_scopes(current_app: AppIdentity, required_scopes: List[str]) -> None:
    missing = [scope for scope in required_scopes if scope not in current_app.scopes]
    if missing:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"缺少权限: {', '.join(missing)}")


def parse_api_key(value: str) -> tuple[str, str] | None:
    match = API_KEY_PATTERN.fullmatch(value.strip())
    return (match.group(1), match.group(2)) if match else None


async def get_current_app(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default="", alias="Authorization"),
    x_app_name: str = Header(default="", alias="X-App-Name"),
) -> AppIdentity:
    scheme, _, credential = authorization.partition(" ")
    parsed = parse_api_key(credential) if scheme.lower() == "bearer" else None
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")
    key_id, secret = parsed
    row = (await db.execute(
        select(ApiKey, OpenPlatformApp)
        .join(OpenPlatformApp, OpenPlatformApp.id == ApiKey.app_id)
        .where(ApiKey.id == key_id)
    )).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")
    key, app = row
    now = datetime.now(timezone.utc)
    expires_at = key.expires_at if key.expires_at.tzinfo else key.expires_at.replace(tzinfo=timezone.utc)
    digest = hashlib.sha256(secret.encode()).hexdigest()
    invalid = (
        not hmac.compare_digest(digest, key.secret_hash)
        or key.status != "active"
        or app.status != "active"
        or expires_at <= now
        or (x_app_name and x_app_name != app.app_name)
    )
    if invalid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")
    last_used = key.last_used_at
    if last_used is None or (last_used if last_used.tzinfo else last_used.replace(tzinfo=timezone.utc)) <= now - timedelta(minutes=5):
        key.last_used_at = now
    return AppIdentity(
        app_id=app.id,
        app_name=app.app_name,
        scopes=list(key.scopes or []),
        key_id=key.id,
    )

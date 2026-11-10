"""OAuth-style service authentication endpoints for APPS."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.service_auth import (
    SERVICE_SCOPE_APPS_WRITE,
    SERVICE_SCOPE_COLLECTIONS_WRITE,
    consume_refresh_token,
    issue_access_token,
    issue_refresh_token,
    verify_client_credentials,
)

router = APIRouter(tags=["service-auth"])
DEFAULT_SCOPES = (SERVICE_SCOPE_APPS_WRITE, SERVICE_SCOPE_COLLECTIONS_WRITE)


def _token_response(access_token: str, expires_in: int, refresh_token: str, refresh_expires_in: int, scope: str):
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "refresh_token": refresh_token,
        "refresh_expires_in": refresh_expires_in,
        "scope": scope,
    }


@router.post("/oauth1/token")
async def token(
    grant_type: Annotated[str, Form()] = "client_credentials",
    client_id: Annotated[str, Form()] = "",
    client_secret: Annotated[str, Form()] = "",
    scope: Annotated[str | None, Form()] = None,
    db: AsyncSession = Depends(get_db),
):
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")
    verify_client_credentials(client_id, client_secret)
    scopes = tuple(item for item in (scope or "").split() if item) or DEFAULT_SCOPES
    allowed = set(get_settings().open_platform_service_scopes.split())
    if any(item not in allowed for item in scopes):
        raise HTTPException(status_code=400, detail="invalid_scope")
    access_token, access_expires = issue_access_token(client_id, scopes)
    refresh_token, refresh_expires = issue_refresh_token(db, client_id, scopes)
    return _token_response(
        access_token,
        access_expires,
        refresh_token,
        refresh_expires,
        " ".join(scopes),
    )


@router.post("/oauth2/refresh")
async def refresh(
    grant_type: Annotated[str, Form()] = "refresh_token",
    client_id: Annotated[str, Form()] = "",
    refresh_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
):
    if grant_type != "refresh_token":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")
    if not client_id or not refresh_token:
        raise HTTPException(status_code=400, detail="invalid_request")
    scopes = await consume_refresh_token(db, refresh_token, client_id)
    if not scopes:
        raise HTTPException(status_code=401, detail="invalid_grant")
    access_token, access_expires = issue_access_token(client_id, scopes)
    next_refresh, refresh_expires = issue_refresh_token(db, client_id, scopes)
    return _token_response(
        access_token,
        access_expires,
        next_refresh,
        refresh_expires,
        " ".join(sorted(scopes)),
    )

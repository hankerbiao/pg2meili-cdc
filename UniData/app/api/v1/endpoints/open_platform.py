"""开放平台管理员会话、应用、API Key 与内部同步端点。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.agents import require_agent_registration_token
from app.api.v1.response import ApiResponse, ok
from app.core.admin_auth import (
    SESSION_COOKIE,
    AdminSession,
    create_admin_session,
    get_admin_session,
    require_admin_csrf,
    verify_admin_password,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.models.open_platform import ApiKey, OpenPlatformApp
from app.services.agent_service import agent_service
from app.services.open_platform_service import open_platform_service


router = APIRouter()
internal_router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class SessionResponse(BaseModel):
    username: str
    csrf_token: str
    expires_at: int


class AppCreateRequest(BaseModel):
    app_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    owner_itcode: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class AppUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    owner_itcode: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "disabled"] | None = None


class AppResponse(BaseModel):
    id: str
    app_name: str
    display_name: str
    owner_itcode: str
    description: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class KeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[Literal["search:read", "data:read", "data:write"]] = Field(min_length=1)
    expires_at: datetime


class AppBootstrapRequest(AppCreateRequest):
    initial_keys: list[KeyCreateRequest] = Field(min_length=1, max_length=2)


class KeyResponse(BaseModel):
    id: str
    app_id: str
    name: str
    prefix: str
    last_four: str
    scopes: list[str]
    status: str
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    version: int
    created_at: datetime


class KeySecretResponse(KeyResponse):
    api_key: str


class AppBootstrapResponse(BaseModel):
    app: AppResponse
    keys: list[KeySecretResponse]


class AuditResponse(BaseModel):
    id: str
    actor: str
    action: str
    target_type: str
    target_id: str | None
    app_id: str | None
    source_ip: str | None
    details: dict | None
    created_at: datetime


class AgentNodeResponse(BaseModel):
    id: str
    ip: str
    port: int
    hostname: str | None
    version: str | None
    region: str
    base_url: str
    weight: int
    status: Literal["online", "offline"]
    is_online: bool
    last_seen_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


def source_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else None)


def serialize_app(app: OpenPlatformApp) -> AppResponse:
    return AppResponse.model_validate(app, from_attributes=True)


def serialize_key(key: ApiKey, plaintext: str | None = None) -> KeyResponse | KeySecretResponse:
    values = {
        "id": key.id,
        "app_id": key.app_id,
        "name": key.name,
        "prefix": f"ud_live_{key.id}",
        "last_four": key.last_four,
        "scopes": list(key.scopes or []),
        "status": key.status,
        "expires_at": key.expires_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
        "version": key.version,
        "created_at": key.created_at,
    }
    return KeySecretResponse(**values, api_key=plaintext) if plaintext else KeyResponse(**values)


@router.post("/session", summary="登录开放平台")
async def login(body: LoginRequest, response: Response, request: Request, db: AsyncSession = Depends(get_db)) -> ApiResponse[SessionResponse]:
    if not verify_admin_password(body.username, body.password):
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token, session = create_admin_session(body.username)
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.open_platform_session_ttl_seconds,
        httponly=True,
        secure=settings.open_platform_cookie_secure,
        samesite="strict",
        path="/",
    )
    open_platform_service.add_audit(db, actor=session.username, action="session.login", target_type="session", source_ip=source_ip(request))
    return ok(SessionResponse(username=session.username, csrf_token=session.csrf_token, expires_at=session.expires_at))


@router.get("/session", summary="获取当前管理员会话")
async def current_session(session: AdminSession = Depends(get_admin_session)) -> ApiResponse[SessionResponse]:
    return ok(SessionResponse(username=session.username, csrf_token=session.csrf_token, expires_at=session.expires_at))


@router.delete("/session", summary="退出开放平台")
async def logout(
    response: Response,
    request: Request,
    session: AdminSession = Depends(require_admin_csrf),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, bool]]:
    response.delete_cookie(SESSION_COOKIE, path="/")
    open_platform_service.add_audit(db, actor=session.username, action="session.logout", target_type="session", source_ip=source_ip(request))
    return ok({"logged_out": True})


@router.get("/apps", summary="获取开放平台应用")
async def list_apps(
    app_status: Literal["active", "disabled"] | None = Query(default=None, alias="status"),
    _: AdminSession = Depends(get_admin_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AppResponse]]:
    return ok([serialize_app(app) for app in await open_platform_service.list_apps(db, app_status)])


@router.post("/apps", status_code=status.HTTP_201_CREATED, summary="创建开放平台应用")
async def create_app(body: AppCreateRequest, request: Request, session: AdminSession = Depends(require_admin_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[AppResponse]:
    app = await open_platform_service.create_app(db, **body.model_dump(), actor=session.username, source_ip=source_ip(request))
    return ok(serialize_app(app))


@router.post(
    "/apps/bootstrap",
    status_code=status.HTTP_201_CREATED,
    summary="创建应用及初始 API Key",
)
async def bootstrap_app(
    body: AppBootstrapRequest,
    request: Request,
    session: AdminSession = Depends(require_admin_csrf),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AppBootstrapResponse]:
    app = await open_platform_service.create_app(
        db,
        **body.model_dump(exclude={"initial_keys"}),
        actor=session.username,
        source_ip=source_ip(request),
    )
    keys: list[KeySecretResponse] = []
    for initial_key in body.initial_keys:
        key, plaintext = await open_platform_service.create_key(
            db,
            app_id=app.id,
            **initial_key.model_dump(),
            actor=session.username,
            source_ip=source_ip(request),
        )
        keys.append(KeySecretResponse.model_validate(serialize_key(key, plaintext)))
    return ok(
        AppBootstrapResponse(
            app=serialize_app(app),
            keys=keys,
        )
    )


@router.get("/apps/{app_id}", summary="获取开放平台应用详情")
async def get_app(app_id: str, _: AdminSession = Depends(get_admin_session), db: AsyncSession = Depends(get_db)) -> ApiResponse[AppResponse]:
    return ok(serialize_app(await open_platform_service.get_app(db, app_id)))


@router.patch("/apps/{app_id}", summary="更新开放平台应用")
async def update_app(app_id: str, body: AppUpdateRequest, request: Request, session: AdminSession = Depends(require_admin_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[AppResponse]:
    changes = body.model_dump(exclude_unset=True)
    app = await open_platform_service.update_app(db, app_id, changes, session.username, source_ip(request))
    return ok(serialize_app(app))


@router.get("/apps/{app_id}/keys", summary="获取应用 API Key")
async def list_keys(app_id: str, _: AdminSession = Depends(get_admin_session), db: AsyncSession = Depends(get_db)) -> ApiResponse[list[KeyResponse]]:
    await open_platform_service.get_app(db, app_id)
    return ok([serialize_key(key) for key in await open_platform_service.list_keys(db, app_id)])


@router.post("/apps/{app_id}/keys", status_code=status.HTTP_201_CREATED, summary="创建应用 API Key")
async def create_key(app_id: str, body: KeyCreateRequest, request: Request, session: AdminSession = Depends(require_admin_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[KeySecretResponse]:
    key, plaintext = await open_platform_service.create_key(db, app_id=app_id, **body.model_dump(), actor=session.username, source_ip=source_ip(request))
    return ok(serialize_key(key, plaintext))


@router.post("/keys/{key_id}/rotate", status_code=status.HTTP_201_CREATED, summary="轮换 API Key")
async def rotate_key(key_id: str, request: Request, session: AdminSession = Depends(require_admin_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[KeySecretResponse]:
    key, plaintext = await open_platform_service.rotate_key(db, key_id, session.username, source_ip(request))
    return ok(serialize_key(key, plaintext))


@router.post("/keys/{key_id}/revoke", summary="撤销 API Key")
async def revoke_key(key_id: str, request: Request, session: AdminSession = Depends(require_admin_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[KeyResponse]:
    key = await open_platform_service.revoke_key(db, key_id, session.username, source_ip(request))
    return ok(serialize_key(key))


@router.get("/audit-logs", summary="获取开放平台审计记录")
async def list_audit_logs(
    app_id: str | None = None,
    action: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: AdminSession = Depends(get_admin_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AuditResponse]]:
    logs = await open_platform_service.list_audit_logs(db, app_id, action, from_time, to_time, offset, limit)
    return ok([AuditResponse.model_validate(item, from_attributes=True) for item in logs])


@router.get("/agents", summary="获取全部代理节点（含离线）")
async def list_agents(
    _: AdminSession = Depends(get_admin_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AgentNodeResponse]]:
    settings = get_settings()
    deadline = datetime.now(timezone.utc) - timedelta(seconds=settings.agent_online_ttl_seconds)
    agents = await agent_service.list_all(db)
    response = []
    for agent in agents:
        meta = agent.meta if isinstance(agent.meta, dict) else {}
        agent_region = str(meta.get("region") or "unknown")
        base_url = str(meta.get("base_url") or f"http://{agent.ip}:{agent.port}").rstrip("/")
        try:
            weight = max(1, min(1000, int(meta.get("weight", 100))))
        except (TypeError, ValueError):
            weight = 100
        online = agent.last_seen_at is not None and agent.last_seen_at >= deadline
        response.append(AgentNodeResponse(
            id=agent.id,
            ip=agent.ip,
            port=agent.port,
            hostname=agent.hostname,
            version=agent.version,
            region=agent_region,
            base_url=base_url,
            weight=weight,
            status="online" if online else "offline",
            is_online=agent.is_online,
            last_seen_at=agent.last_seen_at,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        ))
    return ok(response)


@internal_router.get("/api-keys/snapshot", include_in_schema=False)
async def api_key_snapshot(
    _: None = Depends(require_agent_registration_token),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    return ok(await open_platform_service.snapshot(db))

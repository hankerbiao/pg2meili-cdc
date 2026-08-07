"""开放平台管理员会话、应用、API Key 与内部同步端点。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
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
from app.core.any_auth import ROLE_OA, AnySession, get_any_session, require_any_csrf
from app.core.config import get_settings
from app.core.database import get_db
from app.models.oa import OaUser
from app.models.open_platform import ApiKey, OpenPlatformApp, utc_now
from app.api.v1.validation import valid_collection_name
from app.schemas.document import CollectionDetail, CollectionSettingsUpdate
from app.services.agent_service import agent_service
from app.services.collection_service import collection_service
from app.services import cleanup_service
from app.services.open_platform_service import OpenPlatformService, app_event, open_platform_service


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


class CleanupCollectionStatus(BaseModel):
    collection: str
    status: str
    attempts: int
    error: str | None = None
    finished_at: str | None = None


class CleanupStatusResponse(BaseModel):
    app_id: str
    state: str
    attempts: int
    last_error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    collections: list[CleanupCollectionStatus]


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


def _assert_owned(identity: AnySession, app: OpenPlatformApp) -> None:
    """OA 普通用户只能访问 owner_itcode 为自己的应用；管理员不受限。"""
    if identity.role == ROLE_OA and app.owner_itcode != identity.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该应用")


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
    identity: AnySession = Depends(get_any_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AppResponse]]:
    owner = identity.username if identity.role == ROLE_OA else None
    return ok([serialize_app(app) for app in await open_platform_service.list_apps(db, app_status, owner_itcode=owner)])


@router.post("/apps", status_code=status.HTTP_201_CREATED, summary="创建开放平台应用")
async def create_app(body: AppCreateRequest, request: Request, identity: AnySession = Depends(require_any_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[AppResponse]:
    # 负责人强制为当前登录人本人（前端已无 itcode 输入项，请求体中的 owner_itcode 一律忽略）
    owner_itcode = identity.username
    app = await open_platform_service.create_app(
        db,
        app_name=body.app_name,
        display_name=body.display_name,
        owner_itcode=owner_itcode,
        description=body.description,
        actor=f"{identity.role}:{identity.username}",
        source_ip=source_ip(request),
    )
    return ok(serialize_app(app))


@router.post(
    "/apps/bootstrap",
    status_code=status.HTTP_201_CREATED,
    summary="创建应用及初始 API Key",
)
async def bootstrap_app(
    body: AppBootstrapRequest,
    request: Request,
    identity: AnySession = Depends(require_any_csrf),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AppBootstrapResponse]:
    # 负责人强制为当前登录人本人（与 create_app 一致，请求体中的 owner_itcode 一律忽略）
    owner_itcode = identity.username
    actor = f"{identity.role}:{identity.username}"
    app = await open_platform_service.create_app(
        db,
        app_name=body.app_name,
        display_name=body.display_name,
        owner_itcode=owner_itcode,
        description=body.description,
        actor=actor,
        source_ip=source_ip(request),
    )
    keys: list[KeySecretResponse] = []
    for initial_key in body.initial_keys:
        key, plaintext = await open_platform_service.create_key(
            db,
            app_id=app.id,
            **initial_key.model_dump(),
            actor=actor,
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
async def get_app(app_id: str, identity: AnySession = Depends(get_any_session), db: AsyncSession = Depends(get_db)) -> ApiResponse[AppResponse]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    return ok(serialize_app(app))


@router.patch("/apps/{app_id}", summary="更新开放平台应用")
async def update_app(app_id: str, body: AppUpdateRequest, request: Request, identity: AnySession = Depends(require_any_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[AppResponse]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    changes = body.model_dump(exclude_unset=True)
    if identity.role == ROLE_OA:
        # OA 用户不能转移应用负责人（涉及数据隔离边界）
        if "owner_itcode" in changes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="普通用户不能修改应用负责人")
    app = await open_platform_service.update_app(db, app_id, changes, f"{identity.role}:{identity.username}", source_ip(request))
    return ok(serialize_app(app))


@router.delete("/apps/{app_id}", summary="删除开放平台应用（回收租户资源）")
async def delete_app(
    app_id: str,
    request: Request,
    identity: AnySession = Depends(require_any_csrf),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AppResponse]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    app = await open_platform_service.delete_app(
        db,
        app_id=app_id,
        actor=f"{identity.role}:{identity.username}",
        source_ip=source_ip(request),
    )
    return ok(serialize_app(app))


@router.get("/apps/{app_id}/cleanup", summary="获取应用删除清理任务状态")
async def get_app_cleanup(
    app_id: str,
    identity: AnySession = Depends(get_any_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CleanupStatusResponse]:
    """返回清理状态机进度，供前端展示删除进行中/失败而非假设同步完成（plan §5）。"""
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    task = await cleanup_service.get_task(db, app_id)
    if task is None:
        return ok(CleanupStatusResponse(
            app_id=app_id,
            state=app.status,
            attempts=0,
            last_error=None,
            started_at=None,
            finished_at=None,
            collections=[],
        ))
    return ok(CleanupStatusResponse(
        app_id=task.app_id,
        state=task.state,
        attempts=task.attempts,
        last_error=task.last_error,
        started_at=task.started_at,
        finished_at=task.finished_at,
        collections=[CleanupCollectionStatus(**c) for c in (task.collection_cleanup or [])],
    ))


@router.get("/apps/{app_id}/keys", summary="获取应用 API Key")
async def list_keys(app_id: str, identity: AnySession = Depends(get_any_session), db: AsyncSession = Depends(get_db)) -> ApiResponse[list[KeyResponse]]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    return ok([serialize_key(key) for key in await open_platform_service.list_keys(db, app_id)])


@router.post("/apps/{app_id}/keys", status_code=status.HTTP_201_CREATED, summary="创建应用 API Key")
async def create_key(app_id: str, body: KeyCreateRequest, request: Request, identity: AnySession = Depends(require_any_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[KeySecretResponse]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    key, plaintext = await open_platform_service.create_key(db, app_id=app_id, **body.model_dump(), actor=f"{identity.role}:{identity.username}", source_ip=source_ip(request))
    return ok(serialize_key(key, plaintext))


@router.post("/keys/{key_id}/rotate", status_code=status.HTTP_201_CREATED, summary="轮换 API Key")
async def rotate_key(key_id: str, request: Request, identity: AnySession = Depends(require_any_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[KeySecretResponse]:
    key = await db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    _assert_owned(identity, await open_platform_service.get_app(db, key.app_id))
    key, plaintext = await open_platform_service.rotate_key(db, key_id, f"{identity.role}:{identity.username}", source_ip(request))
    return ok(serialize_key(key, plaintext))


@router.post("/keys/{key_id}/revoke", summary="撤销 API Key")
async def revoke_key(key_id: str, request: Request, identity: AnySession = Depends(require_any_csrf), db: AsyncSession = Depends(get_db)) -> ApiResponse[KeyResponse]:
    key = await db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    _assert_owned(identity, await open_platform_service.get_app(db, key.app_id))
    key = await open_platform_service.revoke_key(db, key_id, f"{identity.role}:{identity.username}", source_ip(request))
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


# ---------------------------------------------------------------------------
# 用户管理（仅管理员）：合并 admin 单例 + OA 普通用户，支持启用/禁用。
# ---------------------------------------------------------------------------
class UserItem(BaseModel):
    """控制台用户列表项。admin 为内置虚拟行（不可禁用）。"""
    itcode: str
    name: str
    email: str
    role: Literal["admin", "oa"]
    status: Literal["active", "disabled"]
    app_count: int
    created_at: datetime | None


class UserListResponse(BaseModel):
    items: list[UserItem]
    total: int


class UserStatusResponse(BaseModel):
    itcode: str
    status: Literal["active", "disabled"]


def _admin_user_item(settings) -> UserItem:
    return UserItem(
        itcode=settings.open_platform_admin_username,
        name=settings.open_platform_admin_username,
        email="",
        role="admin",
        status="active",
        app_count=0,
        created_at=None,
    )


@router.get("/users", summary="获取开放平台用户列表（仅管理员）")
async def list_users(
    keyword: str | None = None,
    user_status: Literal["active", "disabled"] | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: AdminSession = Depends(get_admin_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserListResponse]:
    """合并 admin 单例与 OA 用户；支持关键字（itcode/姓名/邮箱）与状态过滤。"""
    settings = get_settings()
    keyword = (keyword or "").strip().lower()

    # OA 用户查询
    oa_query = select(OaUser)
    if user_status:
        oa_query = oa_query.where(OaUser.status == user_status)
    oa_rows = list((await db.execute(oa_query.order_by(OaUser.created_at.desc()))).scalars().all())

    # 统计每个 OA 用户的应用数（owner_itcode）
    owner_counts: dict[str, int] = {}
    if oa_rows:
        app_rows = (await db.execute(
            select(OpenPlatformApp.owner_itcode, func.count(OpenPlatformApp.id))
            .where(OpenPlatformApp.owner_itcode.in_([r.itcode for r in oa_rows]))
            .group_by(OpenPlatformApp.owner_itcode)
        )).all()
        owner_counts = {row[0]: row[1] for row in app_rows}

    def _matches(u: OaUser) -> bool:
        if not keyword:
            return True
        profile = u.profile if isinstance(u.profile, dict) else {}
        name = str(profile.get("姓名") or profile.get("name") or profile.get("displayName") or "")
        email = str(profile.get("email") or profile.get("邮箱") or "")
        return keyword in u.itcode.lower() or keyword in name.lower() or keyword in email.lower()

    oa_items = [
        UserItem(
            itcode=u.itcode,
            name=str((u.profile or {}).get("姓名") or (u.profile or {}).get("name") or u.itcode),
            email=str((u.profile or {}).get("email") or (u.profile or {}).get("邮箱") or ""),
            role="oa",
            status=u.status,  # type: ignore[arg-type]
            app_count=owner_counts.get(u.itcode, 0),
            created_at=u.created_at,
        )
        for u in oa_rows if _matches(u)
    ]

    # admin 单例虚拟行（恒 active，过滤：关键字/状态命中才纳入）
    admin_item = _admin_user_item(settings)
    admin_hit = (not keyword or keyword in admin_item.itcode.lower()) and (
        user_status is None or user_status == "active"
    )

    # 合并：admin 恒排在最前
    merged = ([admin_item] if admin_hit else []) + oa_items

    total = len(merged)
    page = merged[offset : offset + limit]
    return ok(UserListResponse(items=page, total=total))


async def _set_oa_user_status(
    db: AsyncSession, itcode: str, target: Literal["active", "disabled"], actor: str, source_ip: str | None
) -> None:
    """切换 OA 用户状态，并级联其名下 active 应用（禁用→应用置 disabled，启用→不自动复活应用）。"""
    user = await db.get(OaUser, itcode)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.status == target:
        return
    user.status = target
    user.updated_at = utc_now()
    await db.flush()
    if target == "disabled":
        # 级联：名下 active 应用一并禁用，复用 auth.py 对 App.status 的校验即拒绝其 API Key 调用
        apps = (await db.execute(
            select(OpenPlatformApp).where(
                OpenPlatformApp.owner_itcode == itcode, OpenPlatformApp.status == "active"
            )
        )).scalars().all()
        for app in apps:
            app.status = "disabled"
            app.updated_at = utc_now()
            app.version += 1
            await db.flush()
            OpenPlatformService._add_outbox(db, app.id, "app.upsert", app_event(app))
            open_platform_service.add_audit(
                db, actor=actor, action="app.update", target_type="app", target_id=app.id,
                app_id=app.id, source_ip=source_ip, details={"status": "disabled", "reason": "user_disabled"},
            )
    await db.commit()


@router.post("/users/{itcode}/disable", summary="禁用用户（仅管理员）")
async def disable_user(
    itcode: str,
    identity: AdminSession = Depends(require_admin_csrf),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> ApiResponse[UserStatusResponse]:
    settings = get_settings()
    if itcode == settings.open_platform_admin_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账号不可禁用")
    actor = f"admin:{identity.username}"
    await _set_oa_user_status(db, itcode, "disabled", actor, source_ip(request))
    return ok(UserStatusResponse(itcode=itcode, status="disabled"))


@router.post("/users/{itcode}/enable", summary="启用用户（仅管理员）")
async def enable_user(
    itcode: str,
    identity: AdminSession = Depends(require_admin_csrf),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> ApiResponse[UserStatusResponse]:
    actor = f"admin:{identity.username}"
    await _set_oa_user_status(db, itcode, "active", actor, source_ip(request))
    return ok(UserStatusResponse(itcode=itcode, status="active"))


# ---------------------------------------------------------------------------
# 控制台集合（索引）管理：当前用户（admin/oa）查看其名下应用的集合与设置。
# ---------------------------------------------------------------------------
@router.get("/apps/{app_id}/collections", summary="获取应用下的集合列表")
async def list_app_collections(
    app_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    identity: AnySession = Depends(get_any_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CollectionDetail]]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    return ok(await collection_service.list_collections(db, app_id, limit, offset))


@router.get("/apps/{app_id}/collections/{collection}", summary="获取集合详情")
async def get_app_collection(
    app_id: str,
    collection: str = Depends(valid_collection_name),
    identity: AnySession = Depends(get_any_session),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CollectionDetail]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    return ok(await collection_service.get_collection(db, app_id, collection))


@router.patch(
    "/apps/{app_id}/collections/{collection}/settings",
    summary="更新集合可过滤/可排序设置",
)
async def update_app_collection_settings(
    app_id: str,
    collection: str = Depends(valid_collection_name),
    body: CollectionSettingsUpdate = ...,
    request: Request = None,
    identity: AnySession = Depends(require_any_csrf),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CollectionDetail]:
    app = await open_platform_service.get_app(db, app_id)
    _assert_owned(identity, app)
    detail = await collection_service.update_settings(
        db, app_id, app.app_name, collection, body
    )
    open_platform_service.add_audit(
        db,
        actor=f"{identity.role}:{identity.username}",
        action="collection.update_settings",
        target_type="collection",
        target_id=collection,
        app_id=app_id,
        source_ip=source_ip(request),
        details={"filterable": body.filterableAttributes, "sortable": body.sortableAttributes},
    )
    return ok(detail)

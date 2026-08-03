"""代理节点管理 API 端点。"""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AppIdentity, get_current_app, require_scopes
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.document import AgentRegisterRequest, AgentRegisterResponse, AgentOnlineResponse
from app.services.agent_service import agent_service
from app.api.v1.response import ApiResponse, ok

router = APIRouter()


def require_agent_registration_token(
    x_agent_token: str = Header(default="", alias="X-Agent-Token"),
) -> None:
    expected = get_settings().agent_registration_token.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent 注册服务未配置",
        )
    if not secrets.compare_digest(x_agent_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent 注册凭证无效",
        )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="注册代理节点",
    description="代理服务启动后上报自身信息，用于中心服务登记与健康扫描。",
)
async def register_agent(
    body: AgentRegisterRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_agent_registration_token),
) -> ApiResponse[AgentRegisterResponse]:
    agent = await agent_service.register(
        db=db,
        ip=body.ip,
        port=body.port,
        hostname=body.hostname,
        version=body.version,
        meta=body.meta,
    )
    return ok(AgentRegisterResponse(id=agent.id, ip=agent.ip, port=agent.port))


@router.get(
    "/online",
    status_code=status.HTTP_200_OK,
    summary="获取在线代理列表",
    description="返回当前在线代理的 IP 与端口。",
)
async def list_online_agents(
    region: str | None = Query(default=None, description="按区域筛选 Agent"),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[list[AgentOnlineResponse]]:
    require_scopes(current_app, ["search:read"])
    agents = await agent_service.list_online(db)
    response = []
    for agent in agents:
        if not agent.is_online:
            continue
        meta = agent.meta if isinstance(agent.meta, dict) else {}
        agent_region = str(meta.get("region") or "unknown")
        if region and agent_region != region:
            continue
        base_url = str(meta.get("base_url") or f"http://{agent.ip}:{agent.port}").rstrip("/")
        try:
            weight = max(1, min(1000, int(meta.get("weight", 100))))
        except (TypeError, ValueError):
            weight = 100
        response.append(AgentOnlineResponse(
            id=agent.id,
            ip=agent.ip,
            port=agent.port,
            hostname=agent.hostname,
            base_url=base_url,
            region=agent_region,
            status="ready",
            weight=weight,
            version=agent.version,
            last_seen_at=agent.last_seen_at,
        ))
    return ok(response)

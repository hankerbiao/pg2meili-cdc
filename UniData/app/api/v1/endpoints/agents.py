"""代理节点管理 API 端点。"""
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.document import AgentRegisterRequest, AgentRegisterResponse, AgentOnlineResponse
from app.services.agent_service import agent_service

router = APIRouter()


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册代理节点",
    description="代理服务启动后上报自身信息，用于中心服务登记与健康扫描。",
)
async def register_agent(
    body: AgentRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentRegisterResponse:
    agent = await agent_service.register(
        db=db,
        ip=body.ip,
        port=body.port,
        hostname=body.hostname,
        version=body.version,
        meta=body.meta,
    )
    return AgentRegisterResponse(status="success", id=agent.id, ip=agent.ip, port=agent.port)


@router.get(
    "/online",
    response_model=List[AgentOnlineResponse],
    status_code=status.HTTP_200_OK,
    summary="获取在线代理列表",
    description="返回当前在线代理的 IP 与端口。",
)
async def list_online_agents(
    db: AsyncSession = Depends(get_db),
) -> List[AgentOnlineResponse]:
    agents = await agent_service.list_online(db)
    return [
        AgentOnlineResponse(ip=a.ip, port=a.port, hostname=a.hostname)
        for a in agents
        if a.is_online
    ]

"""代理节点注册与健康管理服务。"""
from datetime import datetime, timezone
from typing import List

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent import AgentNode
from app.repositories.agent_repository import agent_repository


class AgentService:
    """代理节点管理业务逻辑。"""

    @staticmethod
    def build_agent_id(ip: str, port: int) -> str:
        return f"{ip}:{port}"

    @staticmethod
    async def register(
        db: AsyncSession,
        ip: str,
        port: int,
        hostname: str | None,
        version: str | None,
        meta: dict | None,
    ) -> AgentNode:
        agent_id = AgentService.build_agent_id(ip, port)
        return await agent_repository.upsert_agent(
            db=db,
            agent_id=agent_id,
            ip=ip,
            port=port,
            hostname=hostname,
            version=version,
            meta=meta,
        )

    @staticmethod
    async def list_all(db: AsyncSession) -> List[AgentNode]:
        agents = await agent_repository.list_all(db)
        logger.debug("全量代理查询 count={}", len(agents))
        return agents

    @staticmethod
    async def list_online(db: AsyncSession) -> List[AgentNode]:
        settings = get_settings()
        agents = await agent_repository.list_online(db, settings.agent_online_ttl_seconds)
        logger.debug("在线代理查询 ttl={}s count={}", settings.agent_online_ttl_seconds, len(agents))
        return agents

    @staticmethod
    async def check_health(agent: AgentNode) -> bool:
        settings = get_settings()
        url = f"http://{agent.ip}:{agent.port}{settings.agent_health_path}"
        timeout = settings.agent_health_timeout_seconds
        try:
            logger.debug("开始健康检查 url={} agent_id={}", url, agent.id)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                logger.debug("健康检查响应 url={} status={}", url, resp.status_code)
                return resp.status_code == 200
        except Exception as exc:
            logger.debug("代理健康检查失败 {}: {}", url, exc)
            return False

    @staticmethod
    async def update_status(db: AsyncSession, agent: AgentNode, is_online: bool) -> None:
        await agent_repository.update_status(
            db=db,
            agent=agent,
            is_online=is_online,
            last_checked_at=datetime.now(timezone.utc),
        )


agent_service = AgentService()

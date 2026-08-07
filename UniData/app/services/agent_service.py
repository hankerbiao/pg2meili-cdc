"""代理节点注册与健康管理服务。"""
from datetime import datetime, timezone
from typing import List

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    allowed_agent_cidrs,
    validate_agent_address,
    validate_agent_base_url,
)
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
        # SSRF 防护：拒绝 Agent 自报的受限地址，避免中心服务被借作内网探测跳板。
        allowed = allowed_agent_cidrs()
        validate_agent_address(ip, port, allowed_cidrs=allowed)
        if isinstance(meta, dict) and meta.get("base_url"):
            normalized = validate_agent_base_url(str(meta["base_url"]), allowed_cidrs=allowed)
            if normalized is not None:
                meta = {**meta, "base_url": normalized}

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
        # 防御性校验：即使注册环节被绕过，也不对受限地址发起请求。
        try:
            validate_agent_address(agent.ip, agent.port, allowed_cidrs=allowed_agent_cidrs())
        except ValueError as exc:
            logger.warning("跳过受限 Agent 地址的健康检查 {}: {}", agent.id, exc)
            return False
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

"""代理节点仓储层。"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentNode


class AgentRepository:
    """代理节点的数据库访问封装。"""

    @staticmethod
    async def upsert_agent(
        db: AsyncSession,
        agent_id: str,
        ip: str,
        port: int,
        hostname: Optional[str],
        version: Optional[str],
        meta: Optional[Dict[str, Any]],
    ) -> AgentNode:
        stmt = select(AgentNode).where(AgentNode.id == agent_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        # 使用 UTC 的时区感知时间
        now = datetime.utcnow()
        if existing:
            existing.ip = ip
            existing.port = port
            existing.hostname = hostname
            existing.version = version
            existing.meta = meta
            existing.updated_at = now
            existing.last_seen_at = now
        else:
            existing = AgentNode(
                id=agent_id,
                ip=ip,
                port=port,
                hostname=hostname,
                version=version,
                meta=meta,
                is_online=True,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(existing)

        await db.flush()
        return existing

    @staticmethod
    async def list_all(db: AsyncSession) -> List[AgentNode]:
        result = await db.execute(select(AgentNode))
        return list(result.scalars().all())

    @staticmethod
    async def list_online(db: AsyncSession, ttl_seconds: int) -> List[AgentNode]:
        deadline = datetime.utcnow() - timedelta(seconds=ttl_seconds)
        stmt = select(AgentNode).where(AgentNode.last_seen_at.isnot(None), AgentNode.last_seen_at >= deadline)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_status(
        db: AsyncSession,
        agent: AgentNode,
        is_online: bool,
        last_checked_at: Optional[datetime] = None,
    ) -> None:
        agent.is_online = is_online
        agent.last_checked_at = last_checked_at or datetime.utcnow()
        agent.updated_at = datetime.utcnow()
        if is_online:
            agent.last_seen_at = datetime.utcnow()
        await db.flush()


agent_repository = AgentRepository()

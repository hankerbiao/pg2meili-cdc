"""代理节点数据库模型。"""
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


class AgentNode(Base):
    """代理节点注册信息表。"""

    __tablename__ = "agent_nodes"

    id = Column(String, primary_key=True, nullable=False)
    ip = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    hostname = Column(String, nullable=True)
    version = Column(String, nullable=True)
    meta = Column(JSONB, nullable=True)

    is_online = Column(Boolean, nullable=False, default=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AgentNode(id={self.id}, ip={self.ip}, port={self.port})>"

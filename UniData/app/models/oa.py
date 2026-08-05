"""OA 单点登录普通用户模型。"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base
from app.models.open_platform import utc_now


class OaUser(Base):
    __tablename__ = "oa_users"

    itcode = Column(String, primary_key=True, nullable=False)
    profile = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

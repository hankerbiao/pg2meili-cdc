"""OA 单点登录普通用户模型。"""
from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base
from app.models.open_platform import utc_now


class OaUser(Base):
    __tablename__ = "oa_users"

    itcode = Column(String, primary_key=True, nullable=False)
    profile = Column(JSONB, nullable=False)
    # 账号状态：active 正常 / disabled 被管理员禁用（拒绝再次登录与 API Key 调用）
    status = Column(String, nullable=False, default="active", server_default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

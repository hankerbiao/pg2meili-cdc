"""Token 撤销记录模型。"""
from datetime import datetime

from sqlalchemy import Column, DateTime, String

from app.models.base import Base


class TokenRevocation(Base):
    """已撤销的 Token 记录（仅保存 jti）。"""

    __tablename__ = "token_revocations"

    jti = Column(String, primary_key=True, nullable=False)
    app_name = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    revoked_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TokenRevocation(jti={self.jti}, app_name={self.app_name})>"

from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB

from app.models.testcase import Base


class AppToken(Base):
    __tablename__ = "app_tokens"

    id = Column(String, primary_key=True, nullable=False)
    app_name = Column(String, nullable=False)
    token = Column(String, nullable=False, unique=True)
    payload = Column(JSONB, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AppToken(id={self.id}, app_name={self.app_name})>"


"""测试用例的数据库模型模块。"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TestCase(Base):
    """测试用例模型，映射到 test_cases 表。"""

    __tablename__ = "test_cases"

    id = Column(String, primary_key=True, nullable=False)
    payload = Column(JSONB, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TestCase(id={self.id})>"
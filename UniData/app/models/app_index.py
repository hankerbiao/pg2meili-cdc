"""应用索引的数据库模型模块。"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, UniqueConstraint

from app.models.testcase import Base


class AppIndex(Base):
    """应用索引模型，记录每个应用可管理的 Meilisearch 索引。"""

    __tablename__ = "app_indexes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_name = Column(String, nullable=False)
    index_uid = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("app_name", "index_uid", name="uq_app_index"),)


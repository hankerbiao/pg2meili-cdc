"""通用文档的数据库模型模块。"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import JSONB

from app.models.testcase import Base


class Document(Base):
    """通用文档模型，映射到 uni_documents 表。"""

    __tablename__ = "uni_documents"

    id = Column(String, primary_key=True, nullable=False)
    collection = Column(String, nullable=False, index=True, comment="集合名称，如 requirements, bugs")
    app_name = Column(String, nullable=True, index=True)
    payload = Column(JSONB, nullable=True)
    is_delete = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 复合索引：加速按应用和集合的查询
    __table_args__ = (
        Index("idx_collection_app", "collection", "app_name"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, collection={self.collection})>"

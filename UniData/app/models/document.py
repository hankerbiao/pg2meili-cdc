"""通用文档的数据库模型模块。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


def utc_now() -> datetime:
    """返回适配 PostgreSQL TIMESTAMP WITHOUT TIME ZONE 的 UTC 时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Document(Base):
    """通用文档模型，映射到 uni_documents 表。"""

    __tablename__ = "uni_documents"

    row_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    id = Column(String, nullable=False)
    app_id = Column(
        String,
        ForeignKey("open_platform_apps.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    collection = Column(
        String,
        nullable=False,
        index=True,
        comment="集合名称，如 requirements, bugs",
    )
    app_name = Column(String, nullable=False, index=True)
    payload = Column(JSONB, nullable=True)
    is_delete = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "app_id",
            "collection",
            "id",
            name="uq_uni_documents_app_collection_id",
        ),
        Index("ix_uni_documents_app_collection", "app_id", "collection"),
        Index("ix_uni_documents_routing", "app_name", "collection"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, collection={self.collection})>"

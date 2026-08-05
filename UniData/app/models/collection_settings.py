"""集合设置模型（期望态）。

控制台展示与配置的集合设置（可过滤/可排序字段等）以「期望态」持久化在 UniData，
实际下发到 Meilisearch 由 Kafka 命令驱动（见 app.services.index_service）。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CollectionSettings(Base):
    """集合设置，按 (app_id, collection) 唯一。"""

    __tablename__ = "collection_settings"

    id = Column(String, primary_key=True, nullable=False)
    app_id = Column(
        String,
        ForeignKey("open_platform_apps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection = Column(String, nullable=False, index=True)
    filterable_attributes = Column(JSONB, nullable=False, default=list)
    sortable_attributes = Column(JSONB, nullable=False, default=list)
    primary_key_field = Column(String, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("app_id", "collection", name="uq_collection_settings_app_collection"),
    )

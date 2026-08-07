"""应用删除异步清理任务的状态机模型。

对应 docs/plans/2026-08-07-system-optimization.md §5：应用删除是跨 PostgreSQL、
Redis、Kafka、Agent、Meilisearch 的长事务，必须改为可恢复任务。状态机：

    active -> deleting -> indexes_pending -> indexes_done
           -> schema_pending -> deleted
    任意阶段失败 -> cleanup_failed -> 重试或人工恢复

API 事务只把应用标记为 deleting、写 lifecycle_epoch、创建 cleanup task 并返回；
清理由 cleanup_service.run_cleanup_task 推进，可从任意中间状态恢复。
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# 状态常量
CLEANUP_STATE_DELETING = "deleting"
CLEANUP_STATE_INDEXES_PENDING = "indexes_pending"
CLEANUP_STATE_INDEXES_DONE = "indexes_done"
CLEANUP_STATE_SCHEMA_PENDING = "schema_pending"
CLEANUP_STATE_DELETED = "deleted"
CLEANUP_STATE_FAILED = "cleanup_failed"

# 终态：deleted 表示完成；cleanup_failed 表示需重试/人工恢复。
CLEANUP_TERMINAL_STATES = (CLEANUP_STATE_DELETED, CLEANUP_STATE_FAILED)


class AppCleanupTask(Base):
    __tablename__ = "app_cleanup_tasks"

    id = Column(String, primary_key=True, nullable=False)
    app_id = Column(String, nullable=False, index=True)
    app_name = Column(String, nullable=False)
    # 当前状态机阶段
    state = Column(String, nullable=False, default=CLEANUP_STATE_DELETING, index=True)
    # 每个 collection 的清理结果：[{"collection","status","attempts","error","finished_at"}]
    # status: pending | command_sent | confirmed | failed；command_sent 仅表示 Kafka
    # 已接收命令，只有所有区域确认后才能删 schema。
    collection_cleanup = Column(JSONB, nullable=False, default=lambda: [])
    # 任务创建时快照在线 Agent 区域；只有这些区域均确认后才能删除 tenant schema。
    target_regions = Column(JSONB, nullable=True, default=None)
    # 清理任务整体重试次数
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

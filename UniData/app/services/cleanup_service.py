"""应用删除的异步清理任务：可恢复状态机 + worker 入口。

设计要点（plan §5）：
- API 事务只把应用标记为 deleting、写 lifecycle_epoch、创建 cleanup task 并返回；
  实际清理由本模块推进，不依赖单次请求存活。
- 每个 collection 的 Meili index 删除通过 Kafka delete_index 命令下发（幂等，
  不存在视为成功），并记录 status/attempts/error/时间戳。
- PostgreSQL 租户 schema 在 collection 快照后立即删除（drop_tenant），与索引回执解耦；
  同样幂等（DROP SCHEMA IF EXISTS）。
- 任意阶段失败置 cleanup_failed 并保留 last_error，可被重试或人工恢复。
- run_cleanup_task 只 flush 不提交；run_cleanup_task_by_id 走独立会话提交，
  供 Worker（P1 的 lifecycle-cleaner）或请求内调用。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db_context
from app.models.cleanup_task import (
    AppCleanupTask,
    CLEANUP_STATE_DELETED,
    CLEANUP_STATE_DELETING,
    CLEANUP_STATE_FAILED,
    CLEANUP_STATE_INDEXES_DONE,
    CLEANUP_STATE_INDEXES_PENDING,
)
from app.models.collection_settings import CollectionSettings
from app.repositories.document_repository import document_repository
from app.services.agent_service import agent_service
from app.services.index_service import index_service
from app.services.tenant_service import drop_tenant


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 任务创建 / 查询
# ---------------------------------------------------------------------------
async def get_task(db: AsyncSession, app_id: str) -> AppCleanupTask | None:
    return await db.scalar(
        select(AppCleanupTask)
        .where(AppCleanupTask.app_id == app_id)
        .order_by(AppCleanupTask.created_at.desc())
    )


async def create_task(db: AsyncSession, *, app_id: str, app_name: str) -> AppCleanupTask:
    task = AppCleanupTask(
        id=uuid.uuid4().hex,
        app_id=app_id,
        app_name=app_name,
        state=CLEANUP_STATE_DELETING,
    )
    db.add(task)
    await db.flush()
    return task


# ---------------------------------------------------------------------------
# 可恢复状态机
# ---------------------------------------------------------------------------
def _collection_record(task: AppCleanupTask, collection: str) -> dict[str, Any]:
    """获取（不存在则创建）某个 collection 的清理记录。"""
    for rec in task.collection_cleanup:
        if rec.get("collection") == collection:
            return rec
    rec = {
        "collection": collection,
        "status": "pending",
        "attempts": 0,
        "error": None,
        "finished_at": None,
        "confirmed_regions": [],
    }
    task.collection_cleanup.append(rec)
    return rec


def _all_collections_done(task: AppCleanupTask) -> bool:
    return all(rec.get("status") == "confirmed" for rec in task.collection_cleanup)


async def _collections_to_cleanup(
    db: AsyncSession, task: AppCleanupTask
) -> list[str]:
    """合并文档与期望态配置中的集合，避免空索引成为孤儿资源。"""
    # schema 已删除后不能再通过 document_repository 查询：ensure_tenant 会为
    # 仍处于 deleting 的应用懒创建 schema。清理任务中的 collection 列表就是
    # 删除前保存的快照，重试时直接使用它，避免已回收资源被重新创建。
    if getattr(task, "schema_dropped", False):
        return sorted({
            str(record.get("collection"))
            for record in (task.collection_cleanup or [])
            if record.get("collection")
        })

    app_id = task.app_id
    document_collections = {
        collection
        async for collection in document_repository.iter_collections_by_app(
            db, app_id, include_deleted=True
        )
    }
    configured_collections = set(
        (await db.execute(
            select(CollectionSettings.collection).where(CollectionSettings.app_id == app_id)
        )).scalars().all()
    )
    return sorted(document_collections | configured_collections)


async def _snapshot_target_regions(db: AsyncSession) -> list[str]:
    """快照本次删除需要完成 Meilisearch 删除的在线 Agent 区域。"""
    agents = await agent_service.list_online(db)
    regions = {
        str((agent.meta or {}).get("region") or "").strip()
        for agent in agents
        if agent.is_online and str((agent.meta or {}).get("region") or "").strip()
    }
    return sorted(regions)


async def _ensure_target_regions(
    db: AsyncSession, task: AppCleanupTask, collections: list[str]
) -> list[str]:
    if not collections:
        return []
    if not task.target_regions:
        task.target_regions = await _snapshot_target_regions(db)
    regions = sorted({str(region).strip() for region in task.target_regions if str(region).strip()})
    if not regions:
        raise RuntimeError("没有在线且已标识区域的 Agent，无法安全确认索引删除")
    return regions


def record_cleanup_confirmation(task: AppCleanupTask, collection: str, region: str) -> bool:
    """记录一个区域的确认；重复回执是幂等的。"""
    target_regions = {
        str(item).strip() for item in (task.target_regions or []) if str(item).strip()
    }
    if not target_regions:
        raise ValueError("清理任务尚未建立目标区域快照")
    if region not in target_regions:
        raise ValueError(f"区域 {region} 不属于该清理任务")
    rec = next(
        (item for item in task.collection_cleanup if item.get("collection") == collection),
        None,
    )
    if rec is None:
        raise ValueError(f"collection {collection} 不属于该清理任务")
    confirmed = {
        str(item).strip() for item in rec.get("confirmed_regions", []) if str(item).strip()
    }
    if region in confirmed:
        return False
    confirmed.add(region)
    rec["confirmed_regions"] = sorted(confirmed)
    if target_regions.issubset(confirmed):
        rec["status"] = "confirmed"
        rec["error"] = None
        rec["finished_at"] = _utc_now().isoformat()
    return True


async def confirm_cleanup(
    db: AsyncSession, *, task_id: str, collection: str, region: str
) -> AppCleanupTask | None:
    """处理 Agent 删除完成回执，并尝试推进任务的后续阶段。"""
    task = await db.scalar(
        select(AppCleanupTask).where(AppCleanupTask.id == task_id).with_for_update()
    )
    if task is None:
        return None
    if task.state == CLEANUP_STATE_DELETED:
        return task
    record_cleanup_confirmation(task, collection, region)
    flag_modified(task, "collection_cleanup")
    await run_cleanup_task(db, task)
    return task


async def run_cleanup_task(db: AsyncSession, task: AppCleanupTask) -> AppCleanupTask:
    """推进一个应用的清理任务。幂等、可从任意中间状态恢复。

    只 flush 不提交；由调用方（请求事务或 run_cleanup_task_by_id）提交。
    失败时将 state 置为 cleanup_failed 并保留 last_error 后重新抛出，
    允许后续重试（Worker 或重新调用 DELETE /apps/{app_id}）。
    """
    if task.state == CLEANUP_STATE_DELETED:
        return task

    # cleanup_failed：重置为可恢复的中间态后重试，保留已完成的 collection 结果。
    if task.state == CLEANUP_STATE_FAILED:
        task.state = CLEANUP_STATE_INDEXES_PENDING if task.collection_cleanup else CLEANUP_STATE_DELETING
        task.last_error = None

    # 容错：尚未 flush 的任务可能未应用列默认值。
    if task.collection_cleanup is None:
        task.collection_cleanup = []
    if task.started_at is None:
        task.started_at = _utc_now()
    task.attempts = (task.attempts or 0) + 1

    try:
        collections = await _collections_to_cleanup(db, task)
        # 先持久化 collection 快照，再回收 schema。这样即使后续索引清理
        # 因 Agent 不可用而失败，重试也不会触发租户 schema 的懒初始化。
        for collection in collections:
            _collection_record(task, collection)
        flag_modified(task, "collection_cleanup")

        if not getattr(task, "schema_dropped", False):
            await drop_tenant(db, task.app_id)
            task.schema_dropped = True

        had_target_regions = bool(task.target_regions)
        target_regions = await _ensure_target_regions(db, task, collections)
        if target_regions and not had_target_regions:
            # 兼容升级前只有 command_sent 状态的任务：旧命令没有任务 ID，
            # 无法产生回执，必须按新协议重新投递一次。
            for rec in task.collection_cleanup:
                if rec.get("status") == "command_sent":
                    rec["status"] = "pending"

        # 阶段 1：删除各 collection 的 Meili index（Kafka delete_index 命令，幂等）。
        if task.state in (CLEANUP_STATE_DELETING, CLEANUP_STATE_INDEXES_PENDING):
            task.state = CLEANUP_STATE_INDEXES_PENDING
            for collection in collections:
                rec = _collection_record(task, collection)
                if rec["status"] in ("command_sent", "confirmed"):
                    continue
                rec["attempts"] = rec.get("attempts", 0) + 1
                try:
                    await index_service.delete_index_async(
                        app_id=task.app_id,
                        collection=collection,
                        cleanup_task_id=task.id,
                        target_regions=target_regions,
                    )
                    # Kafka flush 仅确认命令已投递；跨区域 Agent 回执前不能
                    # 把应用标记为 deleted，schema 已在此前回收。
                    rec["status"] = "command_sent"
                    rec["error"] = None
                    rec["finished_at"] = _utc_now().isoformat()
                except Exception as exc:  # noqa: BLE001 - 记录后进入 cleanup_failed，可重试
                    rec["status"] = "failed"
                    rec["error"] = str(exc)[:500]
                    task.last_error = f"index {collection}: {exc}"
                    logger.warning("清理租户索引失败 app=%s collection=%s: %s", task.app_id, collection, exc)
                    flag_modified(task, "collection_cleanup")
                    await db.flush()
                    raise

        # 阶段 2：只有区域 Agent 回执确认后才完成 Meilisearch 清理。
        if task.state == CLEANUP_STATE_INDEXES_PENDING and _all_collections_done(task):
            task.state = CLEANUP_STATE_INDEXES_DONE
        if task.state == CLEANUP_STATE_INDEXES_DONE:
            task.state = CLEANUP_STATE_DELETED

        task.finished_at = _utc_now()
        task.updated_at = _utc_now()
        flag_modified(task, "collection_cleanup")
        await db.flush()
        return task
    except Exception as exc:  # noqa: BLE001
        task.state = CLEANUP_STATE_FAILED
        task.last_error = str(exc)[:1000]
        task.updated_at = _utc_now()
        flag_modified(task, "collection_cleanup")
        await db.flush()
        raise


# ---------------------------------------------------------------------------
# worker 入口：按 task id 从独立会话推进（供请求内或 lifecycle-cleaner 调用）
# ---------------------------------------------------------------------------
async def run_cleanup_task_by_id(task_id: str) -> None:
    async with get_db_context() as db:
        task = await db.get(AppCleanupTask, task_id)
        if task is None:
            logger.warning("清理任务不存在 task=%s", task_id)
            return
        try:
            await run_cleanup_task(db, task)
        except Exception:  # noqa: BLE001 - run_cleanup_task 已将状态置为 cleanup_failed
            # 提交失败状态，便于重试与观测；get_db_context 的回滚在无活动事务时为 no-op。
            await db.commit()
            logger.exception("清理任务执行失败 task=%s", task_id)

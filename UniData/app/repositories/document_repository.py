"""通用文档数据库操作的仓储模块。"""
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, utc_now
from app.core.tenant import set_tenant_context, tenant_schema_map
from app.services.tenant_service import ensure_tenant


class DocumentRepository:
    """通用文档 CRUD 操作的仓储类。"""

    @staticmethod
    async def _statement(db: AsyncSession, app_id: str, statement):
        if not isinstance(db, AsyncSession):
            return statement
        await ensure_tenant(db, app_id)
        await set_tenant_context(db, app_id)
        return statement.execution_options(schema_translate_map=tenant_schema_map(app_id))

    @staticmethod
    async def upsert_documents(
        db: AsyncSession,
        app_id: str,
        collection: str,
        app_name: str,
        items: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """在租户唯一键上原子地批量插入或更新文档。"""
        if not items:
            return

        now = utc_now()
        values = [
            {
                "row_id": uuid.uuid4(),
                "id": id_value,
                "app_id": app_id,
                "collection": collection,
                "app_name": app_name,
                "payload": payload,
                "is_delete": False,
                "created_at": now,
                "updated_at": now,
            }
            for id_value, payload in items
        ]
        statement = insert(Document).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[Document.app_id, Document.collection, Document.id],
            set_={
                "app_name": statement.excluded.app_name,
                "payload": statement.excluded.payload,
                "is_delete": False,
                "updated_at": now,
            },
        )
        await db.execute(await DocumentRepository._statement(db, app_id, statement))

    @staticmethod
    async def soft_delete_document(
        db: AsyncSession,
        app_id: str,
        collection: str,
        id: str,
    ) -> bool:
        """软删除文档。"""
        statement = (
            update(Document)
            .where(
                Document.app_id == app_id,
                Document.collection == collection,
                Document.id == id,
                Document.is_delete.is_(False),
            )
            .values(is_delete=True, updated_at=utc_now())
            .returning(Document.row_id)
        )
        result = await db.execute(await DocumentRepository._statement(db, app_id, statement))
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_document(
        db: AsyncSession,
        app_id: str,
        collection: str,
        id: str,
    ) -> Document | None:
        """根据 ID 获取文档。"""
        statement = select(Document).where(
            Document.app_id == app_id,
            Document.collection == collection,
            Document.id == id,
            Document.is_delete.is_(False),
        )
        result = await db.execute(await DocumentRepository._statement(db, app_id, statement))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        app_id: str,
        collection: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Document]:
        """列出文档。"""
        query = (
            select(Document)
            .where(
                Document.app_id == app_id,
                Document.collection == collection,
                Document.is_delete.is_(False),
            )
            .order_by(Document.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(await DocumentRepository._statement(db, app_id, query))
        return result.scalars().all()

    @staticmethod
    async def list_collections_by_app(
        db: AsyncSession,
        app_id: str,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[str]:
        query = select(Document.collection).where(Document.app_id == app_id)
        if not include_deleted:
            query = query.where(Document.is_delete.is_(False))
        query = (
            query.group_by(Document.collection)
            .order_by(Document.collection.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(await DocumentRepository._statement(db, app_id, query))
        rows = result.all()
        return [row[0] for row in rows]

    @staticmethod
    async def iter_collections_by_app(
        db: AsyncSession,
        app_id: str,
        batch_size: int = 500,
        include_deleted: bool = False,
    ) -> AsyncIterator[str]:
        """按批次枚举 collection，避免租户规模影响内存和删除完整性。"""
        offset = 0
        while True:
            batch = await DocumentRepository.list_collections_by_app(
                db,
                app_id,
                limit=batch_size,
                offset=offset,
                include_deleted=include_deleted,
            )
            for collection in batch:
                yield collection
            if len(batch) < batch_size:
                return
            offset += len(batch)

    @staticmethod
    async def get_collection_summaries(
        db: AsyncSession,
        app_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """聚合某应用下的集合摘要：文档数、首末时间、样本字段键。"""
        stats_stmt = (
            select(
                Document.collection,
                func.count(Document.row_id).label("doc_count"),
                func.min(Document.created_at).label("created_at"),
                func.max(Document.updated_at).label("updated_at"),
            )
            .where(Document.app_id == app_id, Document.is_delete.is_(False))
            .group_by(Document.collection)
            .order_by(Document.collection.asc())
            .limit(limit)
            .offset(offset)
        )
        stats_rows = (await db.execute(await DocumentRepository._statement(db, app_id, stats_stmt))).all()

        # 每集合取一条最新样本文档，用于提取字段键（DISTINCT ON 需与 ORDER BY 首列一致）
        sample_stmt = (
            select(Document.collection, Document.payload)
            .where(Document.app_id == app_id, Document.is_delete.is_(False))
            .distinct(Document.collection)
            .order_by(Document.collection.asc(), Document.updated_at.desc())
        )
        sample_rows = (await db.execute(await DocumentRepository._statement(db, app_id, sample_stmt))).all()

        fields_by_collection: dict[str, list[str]] = {}
        for collection, payload in sample_rows:
            if isinstance(payload, dict):
                fields_by_collection[collection] = list(payload.keys())
            else:
                fields_by_collection[collection] = []

        summaries: list[dict[str, Any]] = []
        for collection, doc_count, created_at, updated_at in stats_rows:
            summaries.append({
                "collection": collection,
                "doc_count": doc_count,
                "fields": fields_by_collection.get(collection, []),
                "created_at": created_at,
                "updated_at": updated_at,
            })
        return summaries

    @staticmethod
    async def soft_delete_collection_for_app(
        db: AsyncSession,
        app_id: str,
        collection: str,
    ) -> int:
        statement = (
            update(Document)
            .where(
                Document.collection == collection,
                Document.app_id == app_id,
                Document.is_delete.is_(False),
            )
            .values(
                is_delete=True,
                updated_at=utc_now(),
            )
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(await DocumentRepository._statement(db, app_id, statement))
        return result.rowcount or 0


document_repository = DocumentRepository()

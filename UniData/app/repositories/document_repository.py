"""通用文档数据库操作的仓储模块。"""
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, utc_now


class DocumentRepository:
    """通用文档 CRUD 操作的仓储类。"""

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
        await db.execute(statement)

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
        result = await db.execute(statement)
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
        result = await db.execute(statement)
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

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def list_collections_by_app(
        db: AsyncSession,
        app_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[str]:
        query = (
            select(Document.collection)
            .where(Document.app_id == app_id, Document.is_delete.is_(False))
            .group_by(Document.collection)
            .order_by(Document.collection.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(query)
        rows = result.all()
        return [row[0] for row in rows]

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
        result = await db.execute(statement)
        return result.rowcount or 0


document_repository = DocumentRepository()

"""通用文档数据库操作的仓储模块。"""
import json
from datetime import datetime
from typing import Optional, List, Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    """通用文档 CRUD 操作的仓储类。"""

    @staticmethod
    async def upsert_document(
        db: AsyncSession, 
        collection: str, 
        id: str, 
        app_name: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        插入或更新文档。
        """
        stmt = select(Document).where(Document.id == id, Document.collection == collection)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        now = datetime.utcnow()

        if existing:
            # 确保 app_name 一致性，或者允许修改 app_name？
            # 通常 id 应该是全局唯一的，但这里我们加上 collection 约束，id 在 collection 内唯一？
            # 现在的 PK 是 id，意味着全局唯一。所以 collection 其实是属性。
            # 如果 id 相同但 collection 不同，数据库会报错（主键冲突）。
            # 假设 id 是 UUID 或者业务唯一 ID。
            
            existing.payload = payload
            existing.app_name = app_name # 允许归属变更
            existing.updated_at = now
            existing.is_delete = False # 复活
        else:
            obj = Document(
                id=id, 
                collection=collection,
                app_name=app_name,
                payload=payload, 
                created_at=now,
                updated_at=now
            )
            db.add(obj)

        await db.flush()

    @staticmethod
    async def soft_delete_document(db: AsyncSession, collection: str, id: str) -> bool:
        """软删除文档。"""
        # 为了安全，必须匹配 collection
        stmt = select(Document).where(Document.id == id, Document.collection == collection)
        result = await db.execute(stmt)
        obj = result.scalar_one_or_none()
        
        if not obj:
            return False
            
        obj.is_delete = True
        obj.updated_at = datetime.utcnow()
        await db.flush()
        return True

    @staticmethod
    async def get_document(db: AsyncSession, collection: str, id: str) -> Optional[Document]:
        """根据 ID 获取文档。"""
        stmt = select(Document).where(Document.id == id, Document.collection == collection, Document.is_delete == False)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_documents(
        db: AsyncSession, 
        collection: str, 
        app_name: Optional[str] = None, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Document]:
        """列出文档。"""
        query = select(Document).where(Document.collection == collection, Document.is_delete == False)
        
        if app_name:
            query = query.where(Document.app_name == app_name)
            
        query = query.order_by(Document.updated_at.desc()).limit(limit).offset(offset)
        
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def list_collections_by_app(
        db: AsyncSession,
        app_name: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[str]:
        query = (
            select(Document.collection)
            .where(Document.app_name == app_name, Document.is_delete == False)
            .group_by(Document.collection)
            .order_by(Document.collection.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(query)
        print(result)
        rows = result.all()
        return [row[0] for row in rows]

    @staticmethod
    async def soft_delete_collection_for_app(
        db: AsyncSession,
        collection: str,
        app_name: str,
    ) -> int:
        query = select(Document).where(
            Document.collection == collection,
            Document.app_name == app_name,
            Document.is_delete == False,
        )
        result = await db.execute(query)
        docs = result.scalars().all()
        if not docs:
            return 0

        now = datetime.utcnow()
        for doc in docs:
            doc.is_delete = True
            doc.updated_at = now

        await db.flush()
        return len(docs)


document_repository = DocumentRepository()

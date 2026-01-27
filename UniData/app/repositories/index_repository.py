"""应用索引数据库操作的仓储模块。"""
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_index import AppIndex


class IndexRepository:
    """应用索引 CRUD 操作的仓储类。"""

    @staticmethod
    async def list_indexes(db: AsyncSession, app_name: str) -> List[AppIndex]:
        stmt = select(AppIndex).where(AppIndex.app_name == app_name)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_index(
        db: AsyncSession, app_name: str, index_uid: str
    ) -> Optional[AppIndex]:
        stmt = select(AppIndex).where(
            AppIndex.app_name == app_name, AppIndex.index_uid == index_uid
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def create_index(
        db: AsyncSession, app_name: str, index_uid: str, description: Optional[str]
    ) -> AppIndex:
        obj = AppIndex(
            app_name=app_name,
            index_uid=index_uid,
            description=description,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def update_index(
        db: AsyncSession, app_name: str, index_uid: str, description: Optional[str]
    ) -> Optional[AppIndex]:
        obj = await IndexRepository.get_index(db, app_name, index_uid)
        if not obj:
            return None
        obj.description = description
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def delete_index(
        db: AsyncSession, app_name: str, index_uid: str
    ) -> bool:
        stmt = delete(AppIndex).where(
            AppIndex.app_name == app_name,
            AppIndex.index_uid == index_uid,
        )
        result = await db.execute(stmt)
        return result.rowcount > 0


index_repository = IndexRepository()


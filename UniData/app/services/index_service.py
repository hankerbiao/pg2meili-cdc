"""应用索引业务逻辑模块。"""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_index import AppIndex
from app.repositories.index_repository import index_repository


class IndexService:
    """应用索引相关业务逻辑。"""

    async def list_indexes(self, db: AsyncSession, app_name: str) -> List[AppIndex]:
        return await index_repository.list_indexes(db, app_name)

    async def get_index(
        self, db: AsyncSession, app_name: str, index_uid: str
    ) -> Optional[AppIndex]:
        return await index_repository.get_index(db, app_name, index_uid)

    async def create_index(
        self,
        db: AsyncSession,
        app_name: str,
        index_uid: str,
        description: Optional[str],
    ) -> AppIndex:
        existing = await index_repository.get_index(db, app_name, index_uid)
        if existing:
            return existing
        return await index_repository.create_index(db, app_name, index_uid, description)

    async def update_index(
        self,
        db: AsyncSession,
        app_name: str,
        index_uid: str,
        description: Optional[str],
    ) -> Optional[AppIndex]:
        return await index_repository.update_index(db, app_name, index_uid, description)

    async def delete_index(
        self,
        db: AsyncSession,
        app_name: str,
        index_uid: str,
    ) -> bool:
        return await index_repository.delete_index(db, app_name, index_uid)


index_service = IndexService()


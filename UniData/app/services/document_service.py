"""通用文档业务逻辑的服务层模块。"""
from typing import Any

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import document_repository


class DocumentService:
    """通用文档的业务逻辑类。"""

    @staticmethod
    async def upsert_documents_bulk(
        db: AsyncSession,
        app_id: str,
        collection: str,
        items: list[dict[str, Any]],
        app_name: str,
    ) -> list[str]:
        """批量创建或更新已经过 schema 校验的文档。"""
        ids: list[str] = []
        repository_items: list[tuple[str, dict[str, Any]]] = []
        for payload in items:
            id_value = str(payload["id"])
            payload["collection"] = collection
            payload["app_name"] = app_name
            ids.append(id_value)
            repository_items.append((id_value, payload))

        try:
            await document_repository.upsert_documents(
                db=db,
                app_id=app_id,
                collection=collection,
                app_name=app_name,
                items=repository_items,
            )
        except Exception as e:
            logger.error(f"批量插入文档失败 collection={collection}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )

        return ids

    @staticmethod
    async def delete_document(
        db: AsyncSession,
        app_id: str,
        collection: str,
        id: str,
    ) -> None:
        """
        软删除文档。
        """
        try:
            success = await document_repository.soft_delete_document(
                db,
                app_id,
                collection,
                id,
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"文档不存在或已删除: {id}",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"软删除文档失败 collection={collection} id={id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )

    @staticmethod
    async def get_document(
        db: AsyncSession,
        app_id: str,
        collection: str,
        id: str,
    ) -> dict[str, Any]:
        doc = await document_repository.get_document(db, app_id, collection, id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文档不存在: {id}",
            )
        return doc.payload

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        app_id: str,
        collection: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        docs = await document_repository.list_documents(
            db,
            app_id,
            collection,
            limit,
            offset,
        )
        return [doc.payload for doc in docs if doc.payload]

    @staticmethod
    async def list_collections_for_app(
        db: AsyncSession,
        app_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[str]:
        return await document_repository.list_collections_by_app(
            db=db,
            app_id=app_id,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    async def delete_collection_for_app(
        db: AsyncSession,
        app_id: str,
        collection: str,
    ) -> int:
        try:
            deleted_count = await document_repository.soft_delete_collection_for_app(
                db=db,
                app_id=app_id,
                collection=collection,
            )
            if deleted_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="集合不存在或已为空",
                )
            return deleted_count
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"删除集合失败 collection={collection} app_id={app_id}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )


document_service = DocumentService()

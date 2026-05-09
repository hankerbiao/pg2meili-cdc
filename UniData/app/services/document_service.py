"""通用文档业务逻辑的服务层模块。"""
import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import document_repository
from app.models.document import Document


class DocumentService:
    """通用文档的业务逻辑类。"""

    @staticmethod
    async def upsert_document(
        db: AsyncSession, 
        collection: str, 
        payload: Dict[str, Any],
        app_name: str
    ) -> str:
        """
        创建或更新文档。
        
        collection: 集合名称 (e.g. requirements, bugs)
        payload: 文档内容，必须包含 id
        app_name: 所属应用
        """
        if "id" not in payload or not payload["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少 'id' 字段",
            )

        id_value = str(payload["id"])

        try:
            # 自动注入 collection 到 payload 中，方便后续检索
            payload["collection"] = collection
            payload["app_name"] = app_name
            
            await document_repository.upsert_document(
                db, 
                collection=collection, 
                id=id_value, 
                app_name=app_name, 
                payload=payload
            )
        except Exception as e:
            logger.error(f"插入文档失败 collection={collection} id={id_value}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )

        return id_value

    @staticmethod
    async def upsert_documents_bulk(
        db: AsyncSession,
        collection: str,
        items: List[Dict[str, Any]],
        app_name: str,
    ) -> List[str]:
        """
        批量创建或更新文档。
        items: 文档列表，每个元素必须包含 id
        """
        if not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="items 不能为空",
            )

        ids: List[str] = []
        try:
            for payload in items:
                if "id" not in payload or not payload["id"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="items 中每个元素必须包含非空的 'id' 字段",
                    )
                id_value = str(payload["id"])
                payload["collection"] = collection
                payload["app_name"] = app_name
                await document_repository.upsert_document(
                    db,
                    collection=collection,
                    id=id_value,
                    app_name=app_name,
                    payload=payload,
                )
                ids.append(id_value)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"批量插入文档失败 collection={collection}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )

        return ids

    @staticmethod
    async def delete_document(db: AsyncSession, collection: str, id: str) -> None:
        """
        软删除文档。
        """
        try:
            success = await document_repository.soft_delete_document(db, collection, id)
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
    async def get_document(db: AsyncSession, collection: str, id: str) -> Dict[str, Any]:
        doc = await document_repository.get_document(db, collection, id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文档不存在: {id}",
            )
        return doc.payload

    @staticmethod
    async def list_documents(
        db: AsyncSession, 
        collection: str, 
        app_name: Optional[str] = None, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        docs = await document_repository.list_documents(db, collection, app_name, limit, offset)
        return [doc.payload for doc in docs if doc.payload]

    @staticmethod
    async def list_collections_for_app(
        db: AsyncSession,
        app_name: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[str]:
        return await document_repository.list_collections_by_app(
            db=db,
            app_name=app_name,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    async def delete_collection_for_app(
        db: AsyncSession,
        collection: str,
        app_name: str,
    ) -> int:
        try:
            deleted_count = await document_repository.soft_delete_collection_for_app(
                db=db,
                collection=collection,
                app_name=app_name,
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
            logger.error(f"删除集合失败 collection={collection} app_name={app_name}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )


document_service = DocumentService()

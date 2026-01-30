"""通用文档业务逻辑的服务层模块。"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import document_repository
from app.models.document import Document

logger = logging.getLogger(__name__)


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


document_service = DocumentService()

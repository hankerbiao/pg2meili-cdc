"""索引管理相关 API 端点模块。

负责当前应用在 UniData 中已使用集合（collection）的索引列表查询与索引删除。
"""
from typing import List, Any, Dict

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AppIdentity, get_current_app
from app.core.database import get_db
from app.schemas.document import IndexSettingsRequest, IndexSettingsResponse
from app.services.document_service import document_service
from app.services.index_service import index_service

router = APIRouter()


@router.get(
    "/",
    response_model=List[str],
    status_code=status.HTTP_200_OK,
    summary="获取当前应用下的索引列表",
    description="返回当前应用在 UniData 中已使用的 collection 名称列表。",
)
async def list_app_indexes(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> List[str]:
    collections = await document_service.list_collections_for_app(
        db=db,
        app_name=current_app.app_name,
        limit=limit,
        offset=offset,
    )
    return collections


@router.delete(
    "/{collection}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="删除索引并逻辑删除集合内文档",
    description="对当前应用删除指定 collection 对应的索引，将其中所有文档标记为 is_delete=true。",
)
async def delete_app_index(
    collection: str = Path(..., description="集合名称，如 requirements, bugs"),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> Dict[str, Any]:
    deleted_count = await document_service.delete_collection_for_app(
        db=db,
        collection=collection,
        app_name=current_app.app_name,
    )
    index_service.delete_index(
        app_name=current_app.app_name,
        collection=collection,
    )
    return {
        "status": "success",
        "collection": collection,
        "deleted_count": deleted_count,
    }


@router.post(
    "/{collection}/settings",
    response_model=IndexSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="设置索引可过滤/可排序字段",
    description="接收前端索引设置请求，发送 Kafka 命令同步到各地 Meilisearch。",
)
async def update_index_settings(
    collection: str = Path(..., description="集合名称，如 requirements, bugs"),
    body: IndexSettingsRequest = ...,
    current_app: AppIdentity = Depends(get_current_app),
) -> IndexSettingsResponse:
    index_uid = index_service.update_index_settings(
        app_name=current_app.app_name,
        collection=collection,
        filterable=body.filterableAttributes,
        sortable=body.sortableAttributes,
    )
    return IndexSettingsResponse(
        status="success",
        collection=collection,
        index_uid=index_uid,
    )

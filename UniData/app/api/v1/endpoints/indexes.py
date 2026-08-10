"""索引管理相关 API 端点模块。

负责当前应用在 UniData 中已使用集合（collection）的索引列表查询与索引删除。
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AppIdentity, get_current_app, require_scopes
from app.core.database import get_db
from app.schemas.document import IndexDeleteResponse, IndexSettingsRequest, IndexSettingsResponse
from app.services.document_service import document_service
from app.services.index_service import index_service
from app.api.v1.response import ApiResponse, ok
from app.api.v1.validation import valid_collection_name

router = APIRouter()


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="获取当前应用下的索引列表",
    description="返回当前应用在 UniData 中已使用的 collection 名称列表。",
)
async def list_app_indexes(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[list[str]]:
    require_scopes(current_app, ["data:read"])
    collections = await document_service.list_collections_for_app(
        db=db,
        app_id=current_app.app_id,
        limit=limit,
        offset=offset,
    )
    return ok(collections)


@router.delete(
    "/{collection}",
    status_code=status.HTTP_200_OK,
    summary="删除索引并逻辑删除集合内文档",
    description="对当前应用删除指定 collection 对应的索引，将其中所有文档标记为 is_delete=true。",
)
async def delete_app_index(
    collection: str = Depends(valid_collection_name),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[IndexDeleteResponse]:
    require_scopes(current_app, ["data:write"])
    deleted_count = await document_service.delete_collection_for_app(
        db=db,
        app_id=current_app.app_id,
        collection=collection,
    )
    await index_service.delete_index_async(
        app_id=current_app.app_id,
        collection=collection,
    )
    return ok(IndexDeleteResponse(
        collection=collection,
        deleted_count=deleted_count,
    ))


@router.post(
    "/{collection}/settings",
    status_code=status.HTTP_200_OK,
    summary="设置索引可过滤/可排序字段",
    description="接收前端索引设置请求，发送 Kafka 命令同步到各地 Meilisearch。",
)
async def update_index_settings(
    collection: str = Depends(valid_collection_name),
    body: IndexSettingsRequest = ...,
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[IndexSettingsResponse]:
    require_scopes(current_app, ["data:write"])
    index_uid = await index_service.update_index_settings_async(
        app_id=current_app.app_id,
        collection=collection,
        filterable=body.filterableAttributes,
        sortable=body.sortableAttributes,
    )
    return ok(IndexSettingsResponse(
        collection=collection,
        index_uid=index_uid,
    ))

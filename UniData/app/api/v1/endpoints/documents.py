"""通用文档 API 端点模块。

支持通过 /{collection} 路径管理任意类型的文档（Requirements, Bugs, UserSettings 等）。
"""
from typing import Any

from fastapi import APIRouter, Depends, status, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AppIdentity, get_current_app, require_scopes
from app.core.database import get_db
from app.schemas.document import (
    DocumentCreateRequest,
    DocumentBatchUpsertRequest,
    DocumentBatchUpsertResponse,
    DocumentResponse,
)
from app.services.document_service import document_service
from app.api.v1.response import ApiResponse, ok
from app.api.v1.validation import valid_collection_name

router = APIRouter()


@router.post(
    "/{collection}",
    status_code=status.HTTP_201_CREATED,
    summary="创建/更新通用文档",
    description="向指定集合（collection）中插入或更新文档。请求体必须包含 'id'。",
)
async def upsert_document(
    collection: str = Depends(valid_collection_name),
    body: DocumentCreateRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[DocumentResponse]:
    require_scopes(current_app, ["data:write"])
    id_value = await document_service.upsert_document(
        db,
        app_id=current_app.app_id,
        collection=collection,
        payload=body.model_dump(),
        app_name=current_app.app_name,
    )
    return ok(DocumentResponse(id=id_value, collection=collection))


@router.post(
    "/{collection}/batch",
    status_code=status.HTTP_201_CREATED,
    summary="批量创建/更新通用文档",
    description="向指定集合（collection）中批量插入或更新文档。请求体必须包含 items 列表，且每个元素包含 'id'。",
)
async def upsert_documents_batch(
    collection: str = Depends(valid_collection_name),
    body: DocumentBatchUpsertRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[DocumentBatchUpsertResponse]:
    require_scopes(current_app, ["data:write"])
    payload_items = [item.model_dump() for item in body.items]
    ids = await document_service.upsert_documents_bulk(
        db,
        app_id=current_app.app_id,
        collection=collection,
        items=payload_items,
        app_name=current_app.app_name,
    )

    return ok(DocumentBatchUpsertResponse(
        collection=collection,
        count=len(ids),
        ids=ids,
    ))


@router.get(
    "/{collection}/{id}",
    status_code=status.HTTP_200_OK,
    summary="获取文档详情",
    description="根据集合和 ID 获取文档完整内容。",
)
async def get_document(
    collection: str = Depends(valid_collection_name),
    id: str = Path(..., description="文档 ID"),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[dict[str, Any]]:
    require_scopes(current_app, ["data:read"])
    doc = await document_service.get_document(
        db,
        current_app.app_id,
        collection,
        id,
    )
    return ok(doc)


@router.delete(
    "/{collection}/{id}",
    status_code=status.HTTP_200_OK,
    summary="删除文档",
    description="软删除指定文档。",
)
async def delete_document(
    collection: str = Depends(valid_collection_name),
    id: str = Path(..., description="文档 ID"),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[DocumentResponse]:
    require_scopes(current_app, ["data:write"])
    await document_service.delete_document(
        db,
        current_app.app_id,
        collection,
        id,
    )
    return ok(DocumentResponse(id=id, collection=collection))


@router.get(
    "/{collection}",
    status_code=status.HTTP_200_OK,
    summary="列出集合文档",
    description="分页列出指定集合下的文档。默认只返回当前应用的文档。",
)
async def list_documents(
    collection: str = Depends(valid_collection_name),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
) -> ApiResponse[list[dict[str, Any]]]:
    require_scopes(current_app, ["data:read"])
    docs = await document_service.list_documents(
        db,
        app_id=current_app.app_id,
        collection=collection,
        limit=limit,
        offset=offset,
    )
    return ok(docs)

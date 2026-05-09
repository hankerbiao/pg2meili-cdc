"""通用文档 API 端点模块。

支持通过 /{collection} 路径管理任意类型的文档（Requirements, Bugs, UserSettings 等）。
"""
from typing import List, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AppIdentity, get_current_app_with_revocation, require_scopes
from app.core.database import get_db
from app.schemas.document import (
    DocumentCreateRequest,
    DocumentBatchUpsertRequest,
    DocumentBatchUpsertResponse,
    DocumentResponse,
)
from app.services.document_service import document_service
from app.api.v1.response import ok

router = APIRouter()


@router.post(
    "/{collection}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="创建/更新通用文档",
    description="向指定集合（collection）中插入或更新文档。请求体必须包含 'id'。",
)
async def upsert_document(
    collection: str = Path(..., description="集合名称，如 requirements, bugs"),
    body: DocumentCreateRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app_with_revocation),
) -> DocumentResponse:
    require_scopes(current_app, ["data:write"])
    if not collection or not collection.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="collection 名称只能包含字母、数字、下划线和连字符",
        )

    payload = body.model_dump()
    if "id" not in payload or not payload["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求体必须包含非空的 'id' 字段",
        )
    
    # 执行业务逻辑
    id_value = await document_service.upsert_document(
        db, 
        collection=collection, 
        payload=payload, 
        app_name=current_app.app_name
    )

    return ok(DocumentResponse(status="success", id=id_value, collection=collection).model_dump())


@router.post(
    "/{collection}/batch",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="批量创建/更新通用文档",
    description="向指定集合（collection）中批量插入或更新文档。请求体必须包含 items 列表，且每个元素包含 'id'。",
)
async def upsert_documents_batch(
    collection: str = Path(..., description="集合名称，如 requirements, bugs"),
    body: DocumentBatchUpsertRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app_with_revocation),
) -> DocumentBatchUpsertResponse:
    require_scopes(current_app, ["data:write"])
    if not collection or not collection.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="collection 名称只能包含字母、数字、下划线和连字符",
        )

    payload_items = [item.model_dump() for item in body.items]
    ids = await document_service.upsert_documents_bulk(
        db,
        collection=collection,
        items=payload_items,
        app_name=current_app.app_name,
    )

    return ok(DocumentBatchUpsertResponse(
        status="success",
        collection=collection,
        count=len(ids),
        ids=ids,
    ).model_dump())


@router.get(
    "/{collection}/{id}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="获取文档详情",
    description="根据集合和 ID 获取文档完整内容。",
)
async def get_document(
    collection: str = Path(..., description="集合名称"),
    id: str = Path(..., description="文档 ID"),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app_with_revocation),
) -> Dict[str, Any]:
    require_scopes(current_app, ["data:read"])
    doc = await document_service.get_document(db, collection, id)
    return ok(doc)


@router.delete(
    "/{collection}/{id}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="删除文档",
    description="软删除指定文档。",
)
async def delete_document(
    collection: str = Path(..., description="集合名称"),
    id: str = Path(..., description="文档 ID"),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app_with_revocation),
) -> DocumentResponse:
    require_scopes(current_app, ["data:write"])
    await document_service.delete_document(db, collection, id)
    return ok(DocumentResponse(status="success", id=id, collection=collection).model_dump())


@router.get(
    "/{collection}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="列出集合文档",
    description="分页列出指定集合下的文档。默认只返回当前应用的文档。",
)
async def list_documents(
    collection: str = Path(..., description="集合名称"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app_with_revocation),
) -> List[Dict[str, Any]]:
    require_scopes(current_app, ["data:read"])
    docs = await document_service.list_documents(
        db, 
        collection=collection, 
        app_name=current_app.app_name, 
        limit=limit, 
        offset=offset
    )
    return ok(docs)

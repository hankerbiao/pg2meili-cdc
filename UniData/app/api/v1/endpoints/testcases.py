"""测试用例的 API 端点模块。"""
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AppIdentity, get_current_app
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.testcase import TestCaseResponse, ErrorResponse, MeiliEndpointResponse
from app.services.index_service import index_service
from app.services.testcase_service import testcase_service

router = APIRouter()


@router.post(
    "",
    response_model=TestCaseResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "错误请求"},
        500: {"model": ErrorResponse, "description": "内部服务器错误"},
    },
    summary="创建测试用例",
    description="创建新的测试用例。请求体必须包含 'id' 字段，其他字段作为 JSONB payload 存储。",
)
async def create_test_case(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
    index_uid: str = "",
) -> TestCaseResponse:
    body_bytes = await request.body()

    try:
        json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的 JSON 格式",
        )

    if not index_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 'index_uid' 参数",
        )

    await index_service.create_index(
        db,
        app_name=current_app.app_name,
        index_uid=index_uid,
        description=None,
    )

    id_value = await testcase_service.create_test_case(db, body_bytes)

    return TestCaseResponse(status="success", id=id_value)


@router.put(
    "/{id}",
    response_model=TestCaseResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "错误请求"},
        500: {"model": ErrorResponse, "description": "内部服务器错误"},
    },
    summary="更新测试用例",
    description="根据路径参数 id 更新测试用例，其他字段作为 JSONB payload 存储。",
)
async def update_test_case(
    id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
    index_uid: str = "",
) -> TestCaseResponse:
    if not id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 'id' 参数",
        )

    body_bytes = await request.body()

    try:
        payload = json.loads(body_bytes or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的 JSON 格式",
        )

    if not index_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 'index_uid' 参数",
        )

    await index_service.create_index(
        db,
        app_name=current_app.app_name,
        index_uid=index_uid,
        description=None,
    )

    payload["id"] = id

    try:
        encoded_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法编码为合法的 JSON",
        )

    id_value = await testcase_service.create_test_case(db, encoded_body)

    return TestCaseResponse(status="success", id=id_value)


@router.get(
    "/meilisearch/endpoint",
    response_model=MeiliEndpointResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "错误请求"},
        501: {"model": ErrorResponse, "description": "尚未配置 Meilisearch 端点"},
    },
    summary="获取 Meilisearch 地址",
    description="根据应用名称返回就近的 Meilisearch 服务地址和对应的 API 密钥。",
)
async def get_meilisearch_endpoint(
    app_name: str,
    current_app: AppIdentity = Depends(get_current_app),
) -> MeiliEndpointResponse:
    settings = get_settings()

    if app_name != current_app.app_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权管理该应用的索引",
        )

    if not settings.meili_default_url or not settings.meili_default_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Meilisearch 端点尚未配置",
        )

    return MeiliEndpointResponse(
        app_name=app_name,
        meilisearch_url=settings.meili_default_url,
        api_key=settings.meili_default_api_key,
    )


@router.delete(
    "/{id}",
    response_model=TestCaseResponse,
    responses={
        400: {"model": ErrorResponse, "description": "错误请求"},
        500: {"model": ErrorResponse, "description": "内部服务器错误"},
    },
    summary="删除测试用例",
    description="通过在 payload 中设置 is_delete 为 true 来软删除测试用例。",
)
async def delete_test_case(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_app: AppIdentity = Depends(get_current_app),
    index_uid: str = "",
) -> TestCaseResponse:
    if not id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 'id' 参数",
        )

    if not index_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 'index_uid' 参数",
        )

    await index_service.create_index(
        db,
        app_name=current_app.app_name,
        index_uid=index_uid,
        description=None,
    )

    deleted_id = await testcase_service.delete_test_case(db, id)

    return TestCaseResponse(status="success", id=deleted_id)

"""测试用例的 API 端点模块。

本文件只聚焦 HTTP 层（路由、参数、返回值），
具体业务逻辑下沉到 services 和 repositories 模块，便于 AI 在重构时
区分「接口契约」与「内部实现」。

AI 阅读提示：
- 路由前缀：在 app.api.v1.router 中被挂载到 /api/v1/testcases 之下；
- 请求体验证：统一使用 Pydantic 模型（见 app.schemas.testcase）；
- 数据持久化：统一委托 testcase_service，避免在接口层直接操作数据库。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AppIdentity, get_current_app
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.testcase import (
    MeiliEndpointResponse,
    TestCaseCreateRequest,
    TestCaseResponse,
    TestCaseUpdateRequest,
)
from app.services.testcase_service import testcase_service

router = APIRouter()


def _validate_index_uid(index_uid: str) -> None:
    # 统一校验 index_uid 查询参数，避免在每个端点手动复制 400 逻辑。
    # 如果未来索引路由策略变化，只需在这里集中调整。
    if not index_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 'index_uid' 参数",
        )


@router.post(
    "",
    response_model=TestCaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建测试用例",
    description="创建新的测试用例。请求体必须包含 'id' 字段，其他字段作为 JSONB payload 存储。",
)
async def create_test_case(
        body: TestCaseCreateRequest,
        db: AsyncSession = Depends(get_db),
        current_app: AppIdentity = Depends(get_current_app),
        index_uid: str = "",
) -> TestCaseResponse:
    # 约定：
    # - body 由 TestCaseCreateRequest 解析，至少包含 id 字段；
    # - 允许携带任意额外字段，这些字段将作为 JSONB payload 写入数据库；
    # - app_name 由当前应用身份注入，用于多应用隔离。
    _validate_index_uid(index_uid)

    payload = body.model_dump()
    payload["app_name"] = current_app.app_name

    id_value = await testcase_service.create_test_case(db, payload)

    return TestCaseResponse(status="success", id=id_value)


@router.put(
    "/{id}",
    response_model=TestCaseResponse,
    status_code=status.HTTP_200_OK,
    summary="更新测试用例",
    description="根据路径参数 id 更新测试用例，其他字段作为 JSONB payload 存储。",
)
async def update_test_case(
        id: str,
        body: TestCaseUpdateRequest,
        db: AsyncSession = Depends(get_db),
        current_app: AppIdentity = Depends(get_current_app),
        index_uid: str = "",
) -> TestCaseResponse:
    # 注意：路径参数 id 为「最终权威」，如果 body 中也携带 id，则这里会覆盖。
    # 这样可以保证 URL 清晰表达「要更新哪条用例」，而 body 更像是该用例的字段快照。
    if not id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 'id' 参数",
        )

    _validate_index_uid(index_uid)

    payload = body.model_dump()
    payload["id"] = id
    payload["app_name"] = current_app.app_name

    id_value = await testcase_service.create_test_case(db, payload)

    return TestCaseResponse(status="success", id=id_value)


@router.get(
    "/meilisearch/endpoint",
    response_model=MeiliEndpointResponse,
    status_code=status.HTTP_200_OK,
    summary="获取 Meilisearch 地址",
    description="根据应用名称返回就近的 Meilisearch 服务地址和对应的 API 密钥。",
)
async def get_meilisearch_endpoint(
        app_name: str,
        current_app: AppIdentity = Depends(get_current_app),
) -> MeiliEndpointResponse:
    settings = get_settings()

    if app_name != current_app.app_name:
        # 安全约束：只能管理当前应用自己的索引配置，防止跨应用越权。
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权管理该应用的索引",
        )

    if not settings.meili_default_url or not settings.meili_default_api_key:
        # 部署提示：如果没有在配置中填充 Meilisearch 信息，则认为功能尚未启用。
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Meilisearch 端点尚未配置",
        )

    return MeiliEndpointResponse(
        app_name=app_name,
        meilisearch_url=settings.meili_default_url,
        api_key=settings.meili_default_api_key,
    )

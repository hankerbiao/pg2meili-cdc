"""API v1 路由配置模块。

该模块只负责把各个业务子路由挂载到统一的 `/api/v1` 入口下，
便于在 main.py 中一次性引入。当前仅包含测试用例相关路，由此可以
很清楚地看到对外暴露了哪些一级业务模块。
"""

from fastapi import APIRouter

from app.api.v1.endpoints import testcases_router

# 创建 API v1 顶层路由对象，所有 v1 版本接口都挂在这里
api_router = APIRouter()

# 将测试用例相关接口挂载到 /api/v1/testcases 前缀下
# - prefix: 统一的路径前缀
# - tags: 用于 OpenAPI 文档分组展示
api_router.include_router(
    testcases_router,
    prefix="/testcases",
    tags=["testcases"],
)

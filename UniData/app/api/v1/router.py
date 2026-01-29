"""API v1 路由配置模块。
"""

from fastapi import APIRouter

from app.api.v1.endpoints import testcases_router

api_router = APIRouter()

# 将测试用例相关接口挂载到 /api/v1/testcases 前缀下
api_router.include_router(
    testcases_router,
    prefix="/testcases",
    tags=["testcases"],
)

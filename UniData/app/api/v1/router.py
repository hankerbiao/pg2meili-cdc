"""API v1 路由配置模块。"""
from fastapi import APIRouter
from app.api.v1.endpoints import testcases_router

api_router = APIRouter()

# 在 /api/v1/testcases 下包含测试用例端点
api_router.include_router(
    testcases_router,
    prefix="/testcases",
    tags=["testcases"],
)
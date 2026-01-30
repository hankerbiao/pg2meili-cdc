"""API v1 路由配置模块。
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth_router, testcases_router

api_router = APIRouter()

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    testcases_router,
    prefix="/testcases",
    tags=["testcases"],
)

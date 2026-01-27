"""API v1 路由配置模块。"""
from fastapi import APIRouter
from app.api.v1.endpoints import testcases_router

api_router = APIRouter()

api_router.include_router(
    testcases_router,
    prefix="/testcases",
    tags=["testcases"],
)

"""API v1 路由配置模块。
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth_router, documents_router, indexes_router

api_router = APIRouter()

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    indexes_router,
    prefix="/index/indexes",
    tags=["indexes"],
)

api_router.include_router(
    documents_router,
    prefix="/data",
    tags=["generic-data"],
)

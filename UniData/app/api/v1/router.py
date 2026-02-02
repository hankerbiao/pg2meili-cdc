"""API v1 路由配置模块。
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth_router, documents_router

api_router = APIRouter()

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"],
)

# 注册通用文档路由，挂载到 /data 前缀下，统一管理各类业务集合
api_router.include_router(
    documents_router,
    prefix="/data",
    tags=["generic-data"],
)

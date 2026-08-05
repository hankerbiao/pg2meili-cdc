"""API v1 端点模块入口。"""
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.indexes import router as indexes_router
from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.open_platform import internal_router, router as open_platform_router
from app.api.v1.endpoints.oa import router as oa_router
from app.api.v1.endpoints.sdk import router as sdk_router

__all__ = [
    "documents_router",
    "indexes_router",
    "agents_router",
    "open_platform_router",
    "internal_router",
    "oa_router",
    "sdk_router",
]

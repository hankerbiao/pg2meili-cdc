"""API v1 端点模块入口。"""
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.indexes import router as indexes_router

__all__ = ["auth_router", "documents_router", "indexes_router"]

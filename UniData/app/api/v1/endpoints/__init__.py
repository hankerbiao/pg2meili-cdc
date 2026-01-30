"""API v1 端点模块。"""
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.testcases import router as testcases_router

__all__ = ["auth_router", "testcases_router"]

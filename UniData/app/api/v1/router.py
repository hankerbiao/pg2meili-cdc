"""API v1 路由配置。"""
from fastapi import FastAPI

from app.api.v1.endpoints import (
    agents_router,
    documents_router,
    indexes_router,
    internal_router,
    oa_router,
    open_platform_router,
    sdk_router,
)


ROUTERS = (
    (open_platform_router, "/open-platform", "open-platform"),
    (oa_router, "/auth", "oa-auth"),
    (internal_router, "/internal", "internal"),
    (indexes_router, "/indexes", "indexes"),
    (documents_router, "/data", "generic-data"),
    (agents_router, "/agents", "agents"),
    (sdk_router, "/sdk", "sdk"),
)


def include_api_routes(app: FastAPI) -> None:
    """将业务路由直接挂载到应用，避免嵌套 router 的兼容性差异。"""
    for router, prefix, tag in ROUTERS:
        app.include_router(router, prefix=f"/api/v1{prefix}", tags=[tag])

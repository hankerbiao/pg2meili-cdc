"""API v1 路由配置模块。
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth_router, testcases_router, documents_router

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

# 注册通用文档路由，挂载到根路径或 /documents 下？
# 既然是 /{collection}，直接挂载到 /resources 或者 /documents 可能比较好。
# 如果直接挂载到 /，可能会冲突。
# 建议挂载到 /data 或者 /resources
api_router.include_router(
    documents_router,
    prefix="/data",
    tags=["generic-data"],
)

"""测试用例的 Pydantic 模式定义模块。"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TestCaseCreate(BaseModel):
    """创建测试用例的模式。"""

    id: str = Field(..., description="测试用例 ID（必填）")


class TestCaseResponse(BaseModel):
    """测试用例响应的模式。"""

    status: str = "success"
    id: str


class ErrorResponse(BaseModel):
    """错误响应的模式。"""

    error: str


class MeiliEndpointResponse(BaseModel):
    """获取 Meilisearch 端点的响应模式。"""

    app_name: str = Field(..., description="应用名称")
    meilisearch_url: str = Field(..., description="就近的 Meilisearch 服务地址")
    api_key: str = Field(..., description="用于访问该 Meilisearch 的 API 密钥")

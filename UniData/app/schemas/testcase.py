"""测试用例的 Pydantic 模式定义模块。"""
from pydantic import BaseModel, Field, ConfigDict


class TestCaseBase(BaseModel):
    """测试用例请求的基础字段。"""

    id: str = Field(..., description="测试用例唯一标识")
    model_config = ConfigDict(extra="allow")


class TestCaseCreateRequest(TestCaseBase):
    """创建测试用例的请求模型。"""


class TestCaseUpdateRequest(TestCaseBase):
    """更新测试用例的请求模型。"""


class TestCaseResponse(BaseModel):
    """测试用例响应的模式。"""

    status: str = "success"
    id: str


class MeiliEndpointResponse(BaseModel):
    """获取 Meilisearch 端点的响应模式。"""

    app_name: str = Field(..., description="应用名称")
    meilisearch_url: str = Field(..., description="就近的 Meilisearch 服务地址")
    api_key: str = Field(..., description="用于访问该 Meilisearch 的 API 密钥")

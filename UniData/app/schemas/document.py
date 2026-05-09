"""通用文档的 Pydantic 模式定义模块。"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class DocumentBase(BaseModel):
    """通用文档请求的基础字段。"""
    id: str = Field(..., description="文档唯一标识")
    model_config = ConfigDict(extra="allow")


class DocumentCreateRequest(DocumentBase):
    """创建文档的请求模型。"""
    pass


class DocumentBatchUpsertRequest(BaseModel):
    """批量创建/更新文档的请求模型。"""
    items: List[DocumentCreateRequest] = Field(..., description="文档列表")


class DocumentBatchUpsertResponse(BaseModel):
    """批量创建/更新文档的响应模型。"""
    status: str = "success"
    collection: str
    count: int
    ids: List[str]


class IndexSettingsRequest(BaseModel):
    """索引设置请求（可搜索/可排序字段）。"""
    filterableAttributes: List[str] = Field(..., description="可过滤字段列表")
    sortableAttributes: List[str] = Field(..., description="可排序字段列表")


class IndexSettingsResponse(BaseModel):
    """索引设置请求响应。"""
    status: str = "success"
    collection: str
    index_uid: str


class AgentRegisterRequest(BaseModel):
    """代理节点注册请求。"""
    ip: str = Field(..., description="代理节点 IP")
    port: int = Field(..., description="代理节点端口")
    hostname: Optional[str] = Field(None, description="主机名")
    version: Optional[str] = Field(None, description="代理版本")
    meta: Optional[Dict[str, Any]] = Field(default=None, description="扩展元信息")


class AgentRegisterResponse(BaseModel):
    """代理节点注册响应。"""
    status: str = "success"
    id: str
    ip: str
    port: int


class AgentOnlineResponse(BaseModel):
    """在线代理信息返回模型。"""
    ip: str
    port: int
    hostname: Optional[str] = None


class DocumentResponse(BaseModel):
    """文档响应模式。"""
    status: str = "success"
    id: str
    collection: str



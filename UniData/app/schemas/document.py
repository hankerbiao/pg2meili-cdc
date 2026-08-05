"""通用文档的 Pydantic 模式定义模块。"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentBase(BaseModel):
    """通用文档请求的基础字段。"""
    id: str = Field(..., min_length=1, description="文档唯一标识")
    model_config = ConfigDict(extra="allow")


class DocumentCreateRequest(DocumentBase):
    """创建文档的请求模型。"""
    pass


class DocumentBatchUpsertRequest(BaseModel):
    """批量创建/更新文档的请求模型。"""
    items: List[DocumentCreateRequest] = Field(..., min_length=1, description="文档列表")

    @model_validator(mode="after")
    def validate_unique_document_ids(self):
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("批量请求中的文档 id 不能重复")
        return self


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


class IndexDeleteResponse(BaseModel):
    """索引删除响应。"""
    status: str = "success"
    collection: str
    deleted_count: int


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
    id: str
    ip: str
    port: int
    hostname: Optional[str] = None
    base_url: str
    region: str
    status: str = "ready"
    weight: int = 100
    version: Optional[str] = None
    last_seen_at: Optional[datetime] = None


class DocumentResponse(BaseModel):
    """文档响应模式。"""
    status: str = "success"
    id: str
    collection: str


class CollectionSummary(BaseModel):
    """集合摘要（来自 uni_documents 聚合）。"""
    collection: str
    doc_count: int
    fields: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CollectionDetail(CollectionSummary):
    """集合详情（聚合信息 + 已保存的设置）。"""
    filterable_attributes: List[str] = Field(default_factory=list)
    sortable_attributes: List[str] = Field(default_factory=list)
    primary_key_field: Optional[str] = None


class CollectionSettingsUpdate(BaseModel):
    """集合设置更新请求（可过滤/可排序字段）。"""
    filterableAttributes: List[str] = Field(default_factory=list, description="可过滤字段列表")
    sortableAttributes: List[str] = Field(default_factory=list, description="可排序字段列表")

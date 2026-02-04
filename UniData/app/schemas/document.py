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


class DocumentResponse(BaseModel):
    """文档响应模式。"""
    status: str = "success"
    id: str
    collection: str


class DocumentDetailResponse(BaseModel):
    """文档详情响应。"""
    id: str
    collection: str
    app_name: Optional[str] = None
    payload: Dict[str, Any]

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

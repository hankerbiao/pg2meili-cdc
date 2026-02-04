"""模型模块入口。"""
from app.models.base import Base
from app.models.token import AppToken
from app.models.document import Document

__all__ = ["Base", "AppToken", "Document"]

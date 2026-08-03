"""统一响应封装。"""
from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """API 成功响应。"""

    data: T
    message: str = "ok"


def ok(data: T) -> ApiResponse[T]:
    """统一成功返回格式。"""
    return ApiResponse(data=data)

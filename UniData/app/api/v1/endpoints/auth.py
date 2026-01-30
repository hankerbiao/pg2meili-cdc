"""认证与令牌相关的 API 端点模块。"""
import time
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import generate_jwt
from app.core.database import get_db
from app.services.token_service import token_service


class TokenCreateRequest(BaseModel):
    app_name: str = Field(..., description="应用名称")
    scopes: List[str] = Field(default_factory=list, description="权限列表")
    ttl: int = Field(315360000, description="令牌有效期（秒）")


class TokenResponse(BaseModel):
    token: str = Field(..., description="JWT 令牌")
    app_name: str = Field(..., description="应用名称")
    scopes: List[str] = Field(default_factory=list, description="权限列表")
    expires_at: int = Field(..., description="过期时间戳（秒）")


router = APIRouter()


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="为应用生成访问令牌",
    description="根据 app_name、scopes 和 ttl 生成 JWT 令牌，供前端注册后使用。",
)
async def create_token(
    body: TokenCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token = generate_jwt(body.app_name, body.scopes, body.ttl)
    expires_at = int(time.time()) + body.ttl

    await token_service.save_token(
        db=db,
        token=token,
        app_name=body.app_name,
        scopes=body.scopes,
        expires_at_ts=expires_at,
        request_payload=body.model_dump(),
    )

    return TokenResponse(
        token=token,
        app_name=body.app_name,
        scopes=body.scopes,
        expires_at=expires_at,
    )

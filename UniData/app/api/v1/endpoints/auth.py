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
    itcode: str = Field(..., description="接收 token 的 itcode")
    scopes: List[str] = Field(default_factory=list, description="权限列表")
    ttl: int = Field(315360000, description="令牌有效期（秒）")


class TokenResponse(BaseModel):
    app_name: str = Field(..., description="应用名称")
    itcode: str = Field(..., description="接收 token 的 itcode")
    expires_at: int = Field(..., description="过期时间戳（秒）")


class TokenRecord(BaseModel):
    id: str
    app_name: str
    itcode: str
    expires_at: str
    created_at: str


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
        itcode=body.itcode,
        expires_at_ts=expires_at,
        request_payload=body.model_dump(),
    )

    return TokenResponse(app_name=body.app_name, itcode=body.itcode, expires_at=expires_at)


@router.get(
    "/tokens/pending",
    response_model=List[TokenRecord],
    summary="获取待审核 token 列表",
)
async def list_pending_tokens(
    db: AsyncSession = Depends(get_db),
) -> List[TokenRecord]:
    items = await token_service.list_pending_tokens(db)
    return [
        TokenRecord(
            id=i.id,
            app_name=i.app_name,
            itcode=i.itcode,
            expires_at=i.expires_at.isoformat() if i.expires_at else "",
            created_at=i.created_at.isoformat() if i.created_at else "",
        )
        for i in items
    ]


@router.get(
    "/tokens/approved",
    response_model=List[TokenRecord],
    summary="获取已审核 token 列表",
)
async def list_approved_tokens(
    db: AsyncSession = Depends(get_db),
) -> List[TokenRecord]:
    items = await token_service.list_approved_tokens(db)
    return [
        TokenRecord(
            id=i.id,
            app_name=i.app_name,
            itcode=i.itcode,
            expires_at=i.expires_at.isoformat() if i.expires_at else "",
            created_at=i.created_at.isoformat() if i.created_at else "",
        )
        for i in items
    ]


@router.post(
    "/tokens/{token_id}/approve",
    summary="审核通过指定 token 并发送消息",
)
async def approve_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    obj = await token_service.approve_token(db, token_id)
    expires_at_ts = int(time.mktime(obj.expires_at.timetuple())) if obj.expires_at else 0
    return TokenResponse(app_name=obj.app_name, itcode=obj.itcode, expires_at=expires_at_ts)

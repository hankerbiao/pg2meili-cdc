"""Token 相关业务服务。"""
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.token_repository import token_repository


class TokenService:
    """Token 业务逻辑层，负责保存、查询、审核以及通知。"""
    SEARCH_SCOPES = ["search:read"]
    DATA_SCOPES = ["data:read", "data:write"]
    @staticmethod
    def _mask_token(token: str) -> str:
        if not token:
            return "**"
        if len(token) <= 10:
            masked = f"{token[:2]}**{token[-2:]}"
        else:
            masked = f"{token[:6]}**{token[-4:]}"
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]
        return f"{masked}-{digest}"

    @staticmethod
    async def save_token(
        db: AsyncSession,
        app_name: str,
        scopes: List[str],
        itcode: str,
        expires_at_ts: int,
        request_payload: Dict[str, Any],
    ) -> None:
        # 同一 app_name 只允许存在一条 token 记录
        existing = await token_repository.get_token_by_app_name(db, app_name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="app_name 已存在，请更换应用名称",
            )

        try:
            expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OSError) as e:
            logger.error(f"无效的过期时间戳: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="内部服务器错误",
            )

        # 保存原始申请信息，便于审计与追溯
        payload = {
            "app_name": app_name,
            "scopes": scopes,
            "itcode": itcode,
            "expires_at_ts": expires_at_ts,
            "request": request_payload,
        }

        try:
            placeholder = f"pending**{uuid.uuid4().hex[:12]}"
            await token_repository.insert_token(
                db=db,
                app_name=app_name,
                itcode=itcode,
                jti=placeholder,
                expires_at=expires_at,
                payload=payload,
            )
        except Exception as e:
            logger.error(f"保存 token 失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库错误",
            )

    @staticmethod
    async def list_pending_tokens(db: AsyncSession):
        return await token_repository.list_pending_tokens(db)

    @staticmethod
    async def list_approved_tokens(db: AsyncSession):
        return await token_repository.list_approved_tokens(db)

    @staticmethod
    async def approve_token(db: AsyncSession, token_id: str):
        obj = await token_repository.get_token(db, token_id)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到指定的 token",
            )
        if obj.is_approved:
            return obj

        now_ts = int(datetime.now(timezone.utc).timestamp())
        expires_at_ts = (
            int(obj.expires_at.replace(tzinfo=timezone.utc).timestamp())
            if obj.expires_at
            else now_ts
        )
        ttl_seconds = max(1, expires_at_ts - now_ts)

        search_jti = str(uuid.uuid4())
        data_jti = str(uuid.uuid4())
        from app.core.auth import generate_jwt

        search_token = generate_jwt(obj.app_name, TokenService.SEARCH_SCOPES, ttl_seconds, jti=search_jti)
        data_token = generate_jwt(obj.app_name, TokenService.DATA_SCOPES, ttl_seconds, jti=data_jti)

        obj.jti = f"search:{search_jti};data:{data_jti}"
        await token_repository.approve_token(db, obj)
        await TokenService._send_gquan_message(
            user_itcode=obj.itcode,
            title="UniData Token 审核通过",
            description=f"应用 {obj.app_name} 的访问 Token 已审核通过",
            content_or_url=(
                "【搜索只读 Token】\n"
                f"{search_token}\n\n"
                "【后端读写 Token】\n"
                f"{data_token}"
            ),
        )
        return obj

    @staticmethod
    async def _send_gquan_message(
        user_itcode: str,
        msg_type: str = "MSG",
        title: str = "",
        description: str = "",
        content_or_url: str = "",
    ) -> None:
        settings = get_settings()
        base_url = getattr(settings, "gquan_base_url", "http://10.32.129.1/springboard_v3")

        form_data = {
            "msg_type": msg_type,
            "to_itcode": user_itcode,
            "title": title,
            "desc": description,
            "content_or_url": content_or_url,
        }
        gquan_url = f"{base_url.rstrip('/')}/send_gquan_msg/searchunidatainterface"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(gquan_url, data=form_data)
            try:
                res.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("发送 gquan 消息失败: {}, status={}, body={}", e, res.status_code, res.text)
                return
            try:
                resp_json = res.json()
            except ValueError:
                logger.error("gquan 响应不是 JSON, body={}", res.text)
                return
            data = resp_json.get("data", "")
            message = resp_json.get("message", "")
            if data != "ok":
                logger.error("发送 gquan 消息失败: {}, resp={}", message, resp_json)
            else:
                logger.info("gquan 消息发送成功")
        except Exception as e:
            logger.error("发送 gquan 消息异常: {}", e)


token_service = TokenService()

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.token_repository import token_repository

logger = logging.getLogger(__name__)


class TokenService:
    @staticmethod
    async def save_token(
        db: AsyncSession,
        token: str,
        app_name: str,
        scopes: List[str],
        itcode: str,
        expires_at_ts: int,
        request_payload: Dict[str, Any],
    ) -> None:
        try:
            expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OSError) as e:
            logger.error(f"无效的过期时间戳: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="内部服务器错误",
            )

        payload = {
            "app_name": app_name,
            "scopes": scopes,
            "itcode": itcode,
            "expires_at_ts": expires_at_ts,
            "request": request_payload,
        }

        try:
            await token_repository.insert_token(
                db=db,
                app_name=app_name,
                itcode=itcode,
                token=token,
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
        await token_repository.approve_token(db, obj)
        TokenService._send_gquan_message(
            user_itcode=obj.itcode,
            title="UniData Token 审核通过",
            description=f"应用 {obj.app_name} 的访问 Token 已审核通过",
            content_or_url=obj.token,
        )
        return obj

    @staticmethod
    def _send_gquan_message(
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
            res = requests.post(gquan_url, data=form_data, timeout=15)
            try:
                res.raise_for_status()
            except requests.HTTPError as e:
                logger.error(
                    "发送 gquan 消息失败: %s, status=%s, body=%s",
                    e,
                    res.status_code,
                    res.text,
                )
                return
            try:
                resp_json = res.json()
            except ValueError:
                logger.error("gquan 响应不是 JSON, body=%s", res.text)
                return
            data = resp_json.get("data", "")
            message = resp_json.get("message", "")
            if data != "ok":
                logger.error("发送 gquan 消息失败: %s, resp=%s", message, resp_json)
            else:
                logger.info("gquan 消息发送成功")
        except Exception as e:
            logger.error("发送 gquan 消息异常: %s", e)


token_service = TokenService()

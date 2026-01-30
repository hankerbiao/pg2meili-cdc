import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.token_repository import token_repository

logger = logging.getLogger(__name__)


class TokenService:
    @staticmethod
    async def save_token(
        db: AsyncSession,
        token: str,
        app_name: str,
        scopes: List[str],
        expires_at_ts: int,
        request_payload: Dict[str, Any],
    ) -> None:
        try:
            expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc)
        except (TypeError, ValueError, OSError) as e:
            logger.error(f"无效的过期时间戳: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="内部服务器错误",
            )

        payload = {
            "app_name": app_name,
            "scopes": scopes,
            "expires_at_ts": expires_at_ts,
            "request": request_payload,
        }

        try:
            await token_repository.insert_token(
                db=db,
                app_name=app_name,
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


token_service = TokenService()


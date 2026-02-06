"""Token 撤销服务。"""
import time

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.kafka_manager import get_kafka_manager
from app.repositories.token_revocation_repository import token_revocation_repository


class TokenRevocationService:
    """Token 撤销业务逻辑。"""

    @staticmethod
    def _broadcast_revocation(jti: str, app_name: str, reason: str | None = None) -> None:
        settings = get_settings()
        kafka = get_kafka_manager()
        now_ts = int(time.time())
        kafka.send_json(
            topic=settings.kafka_token_revoke_topic,
            key=app_name,
            payload={
                "version": 1,
                "event": "token_revoked",
                "app_name": app_name,
                "jti": jti,
                "reason": reason,
                "ts": now_ts,
            },
        )
        kafka.flush()

    @staticmethod
    async def revoke(db: AsyncSession, jti: str, app_name: str, reason: str | None = None) -> None:
        if await token_revocation_repository.is_revoked(db, jti):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该 token 已撤销",
            )
        await token_revocation_repository.revoke(
            db=db,
            jti=jti,
            app_name=app_name,
            reason=reason,
        )
        try:
            TokenRevocationService._broadcast_revocation(jti=jti, app_name=app_name, reason=reason)
        except Exception as exc:
            logger.error("发送 token 撤销广播失败: {}", exc)

    @staticmethod
    async def is_revoked(db: AsyncSession, jti: str) -> bool:
        return await token_revocation_repository.is_revoked(db, jti)


token_revocation_service = TokenRevocationService()

"""Token 撤销记录仓储层。"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_revocation import TokenRevocation


class TokenRevocationRepository:
    """Token 撤销记录相关数据库操作。"""

    @staticmethod
    async def get_revocation(db: AsyncSession, jti: str) -> Optional[TokenRevocation]:
        return await db.get(TokenRevocation, jti)

    @staticmethod
    async def is_revoked(db: AsyncSession, jti: str) -> bool:
        result = await db.execute(select(TokenRevocation).where(TokenRevocation.jti == jti).limit(1))
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def revoke(
        db: AsyncSession,
        jti: str,
        app_name: str,
        reason: str | None = None,
    ) -> None:
        obj = TokenRevocation(
            jti=jti,
            app_name=app_name,
            reason=reason,
            revoked_at=datetime.now(timezone.utc),
        )
        db.add(obj)
        await db.flush()


token_revocation_repository = TokenRevocationRepository()

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import AppToken


class TokenRepository:
    @staticmethod
    async def insert_token(
        db: AsyncSession,
        app_name: str,
        itcode: str,
        token: str,
        expires_at: datetime,
        payload: Dict[str, Any],
    ) -> None:
        obj = AppToken(
            id=f"{app_name}-{int(datetime.utcnow().timestamp())}",
            app_name=app_name,
            itcode=itcode,
            token=token,
            expires_at=expires_at,
            payload=payload,
            created_at=datetime.utcnow(),
        )
        db.add(obj)
        await db.flush()

    @staticmethod
    async def list_pending_tokens(db: AsyncSession) -> List[AppToken]:
        result = await db.execute(select(AppToken).where(AppToken.is_approved.is_(False)))
        return list(result.scalars().all())

    @staticmethod
    async def list_approved_tokens(db: AsyncSession) -> List[AppToken]:
        result = await db.execute(select(AppToken).where(AppToken.is_approved.is_(True)))
        return list(result.scalars().all())

    @staticmethod
    async def get_token(db: AsyncSession, token_id: str) -> Optional[AppToken]:
        return await db.get(AppToken, token_id)

    @staticmethod
    async def approve_token(db: AsyncSession, token_obj: AppToken) -> None:
        token_obj.is_approved = True
        token_obj.approved_at = datetime.utcnow()
        await db.flush()


token_repository = TokenRepository()

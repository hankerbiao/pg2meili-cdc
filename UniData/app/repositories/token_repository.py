from datetime import datetime
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import AppToken


class TokenRepository:
    @staticmethod
    async def insert_token(
        db: AsyncSession,
        app_name: str,
        token: str,
        expires_at: datetime,
        payload: Dict[str, Any],
    ) -> None:
        obj = AppToken(
            id=f"{app_name}-{int(datetime.utcnow().timestamp())}",
            app_name=app_name,
            token=token,
            expires_at=expires_at,
            payload=payload,
            created_at=datetime.utcnow(),
        )
        db.add(obj)
        await db.flush()


token_repository = TokenRepository()


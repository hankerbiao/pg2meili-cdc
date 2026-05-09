"""Token 持久化仓储层。"""
from datetime import datetime,timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import AppToken


class TokenRepository:
    """Token 相关的数据库访问仓储，封装所有与 AppToken 有关的操作。"""

    @staticmethod
    async def insert_token(
        db: AsyncSession,
        app_name: str,
        itcode: str,
        jti: str,
        expires_at: datetime,
        payload: Dict[str, Any],
    ) -> None:
        """插入一条待审批的 Token 记录。"""
        obj = AppToken(
            id=f"{app_name}-{int(datetime.now(timezone.utc).timestamp())}",
            app_name=app_name,
            itcode=itcode,
            jti=jti,
            expires_at=expires_at,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        db.add(obj)
        await db.flush()

    @staticmethod
    async def list_pending_tokens(db: AsyncSession) -> List[AppToken]:
        """查询所有未审批的 Token。"""
        result = await db.execute(select(AppToken).where(AppToken.is_approved.is_(False)))
        return list(result.scalars().all())

    @staticmethod
    async def list_approved_tokens(db: AsyncSession) -> List[AppToken]:
        """查询所有已审批通过的 Token。"""
        result = await db.execute(select(AppToken).where(AppToken.is_approved.is_(True)))
        return list(result.scalars().all())

    @staticmethod
    async def get_token(db: AsyncSession, token_id: str) -> Optional[AppToken]:
        """根据主键 ID 获取单条 Token 记录。"""
        return await db.get(AppToken, token_id)

    @staticmethod
    async def get_token_by_app_name(db: AsyncSession, app_name: str) -> Optional[AppToken]:
        """根据 app_name 获取一条 Token 记录（用于唯一性检查）。"""
        result = await db.execute(
            select(AppToken).where(AppToken.app_name == app_name).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def approve_token(db: AsyncSession, token_obj: AppToken) -> None:
        """将指定 Token 标记为已审批，并更新时间。"""
        token_obj.is_approved = True
        token_obj.approved_at = datetime.now(timezone.utc)
        await db.flush()


token_repository = TokenRepository()

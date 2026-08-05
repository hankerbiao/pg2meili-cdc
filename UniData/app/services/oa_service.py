"""OA 普通用户记录与查询服务。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oa import OaUser


async def upsert_oa_user(db: AsyncSession, itcode: str, profile: dict[str, Any]) -> None:
    """记录或更新 OA 登录用户：itcode 主键，profile 存完整 JWT 载荷。"""
    now = datetime.now(timezone.utc)
    stmt = pg_insert(OaUser).values(
        itcode=itcode,
        profile=profile,
        created_at=now,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["itcode"],
        set_={"profile": profile, "updated_at": now},
    )
    await db.execute(stmt)
    await db.commit()


async def get_oa_user_profile(db: AsyncSession, itcode: str) -> dict[str, Any] | None:
    """读取 OA 用户完整资料（profile）。"""
    result = await db.execute(select(OaUser).where(OaUser.itcode == itcode))
    row = result.scalar_one_or_none()
    if row is None or row.profile is None:
        return None
    return dict(row.profile)

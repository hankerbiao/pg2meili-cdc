"""在物理租户迁移完成后显式删除旧的 public.uni_documents。"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.database import engine  # noqa: E402


MIGRATION_VERSION = "20260806_drop_legacy_documents"
PHYSICAL_TENANCY_VERSION = "20260805_physical_tenancy"


async def migrate() -> None:
    if os.getenv("CONFIRM_DROP_LEGACY_DOCUMENTS") != "YES":
        raise RuntimeError("删除旧文档表前必须设置 CONFIRM_DROP_LEGACY_DOCUMENTS=YES")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS unidata_schema_migrations ("
                "version VARCHAR PRIMARY KEY, "
                "applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
            )
        )
        applied = await connection.scalar(
            text("SELECT 1 FROM unidata_schema_migrations WHERE version = :version"),
            {"version": MIGRATION_VERSION},
        )
        if applied:
            return
        migrated = await connection.scalar(
            text("SELECT 1 FROM unidata_schema_migrations WHERE version = :version"),
            {"version": PHYSICAL_TENANCY_VERSION},
        )
        if not migrated:
            raise RuntimeError("物理租户迁移尚未完成，拒绝删除旧文档表")
        await connection.execute(text("DROP TABLE IF EXISTS public.uni_documents"))
        await connection.execute(
            text(
                "INSERT INTO unidata_schema_migrations (version) VALUES (:version) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": MIGRATION_VERSION},
        )


if __name__ == "__main__":
    asyncio.run(migrate())

"""创建开放平台表并删除不再使用的 Token 表。"""

import asyncio
import os
import sys

from sqlalchemy import text

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.database import engine  # noqa: E402
from app.models import Base  # noqa: E402
from migrations.migrate_document_tenancy import (  # noqa: E402
    apply_document_tenancy_migration,
)


MIGRATION_VERSION = "20260730_open_platform_api_keys"


async def migrate() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("""
            CREATE TABLE IF NOT EXISTS unidata_schema_migrations (
                version VARCHAR PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        )
        await connection.run_sync(Base.metadata.create_all)
        applied = await connection.scalar(
            text("SELECT 1 FROM unidata_schema_migrations WHERE version = :version"),
            {"version": MIGRATION_VERSION},
        )
        if not applied:
            await connection.execute(text("DROP TABLE IF EXISTS token_revocations"))
            await connection.execute(text("DROP TABLE IF EXISTS app_tokens"))
            await connection.execute(
                text(
                    "INSERT INTO unidata_schema_migrations (version) VALUES (:version)"
                ),
                {"version": MIGRATION_VERSION},
            )
        await apply_document_tenancy_migration(connection)


if __name__ == "__main__":
    asyncio.run(migrate())
    print(f"数据库迁移完成: {MIGRATION_VERSION}")

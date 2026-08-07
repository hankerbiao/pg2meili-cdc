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
from app.services.tenant_service import ensure_collection_settings_rls  # noqa: E402
from migrations.migrate_document_tenancy import (  # noqa: E402
    apply_document_tenancy_migration,
)
from migrations.migrate_physical_tenancy import (  # noqa: E402
    apply_physical_tenancy_migration,
)


# oa_users 增加 status 列（active / disabled），默认 active，兼容已有数据。
_OA_USER_STATUS_SQL = """
ALTER TABLE oa_users
    ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'active';
"""

# collection_settings 扩展配置列（create_all 对已存在表不加列，必须 ALTER 双保险）。
_COLLECTION_SETTINGS_EXTEND_SQL = """
ALTER TABLE collection_settings
    ADD COLUMN IF NOT EXISTS searchable_attributes JSONB,
    ADD COLUMN IF NOT EXISTS displayed_attributes JSONB,
    ADD COLUMN IF NOT EXISTS distinct_attribute VARCHAR,
    ADD COLUMN IF NOT EXISTS typo_tolerance_enabled BOOLEAN,
    ADD COLUMN IF NOT EXISTS pagination_max_total_hits INTEGER,
    ADD COLUMN IF NOT EXISTS faceting_max_values_per_facet INTEGER;
"""

_CLEANUP_TASKS_EXTEND_SQL = """
ALTER TABLE app_cleanup_tasks
    ADD COLUMN IF NOT EXISTS target_regions JSONB;
"""


MIGRATION_VERSION = "20260730_open_platform_api_keys"
MIGRATION_VERSION_OA_USER_STATUS = "20260805_oa_user_status"
MIGRATION_VERSION_COLLECTION_SETTINGS = "20260805_collection_settings"
MIGRATION_VERSION_COLLECTION_SETTINGS_EXTEND = "20260805_collection_settings_extend"
MIGRATION_VERSION_COLLECTION_SETTINGS_RLS = "20260806_collection_settings_rls"
MIGRATION_VERSION_CLEANUP_TASKS_REGIONS = "20260807_cleanup_task_regions"


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
        # 为 oa_users 增加 status 列（兼容已存在的表，幂等）。
        await connection.execute(text(_OA_USER_STATUS_SQL))
        await connection.execute(
            text(
                "INSERT INTO unidata_schema_migrations (version) VALUES (:version) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": MIGRATION_VERSION_OA_USER_STATUS},
        )
        # collection_settings 表由 Base.metadata.create_all 幂等创建（上方已执行）。
        await connection.execute(
            text(
                "INSERT INTO unidata_schema_migrations (version) VALUES (:version) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": MIGRATION_VERSION_COLLECTION_SETTINGS},
        )
        # 扩展配置列：对已存在的 collection_settings 表补列（幂等）。
        await connection.execute(text(_COLLECTION_SETTINGS_EXTEND_SQL))
        await connection.execute(
            text(
                "INSERT INTO unidata_schema_migrations (version) VALUES (:version) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": MIGRATION_VERSION_COLLECTION_SETTINGS_EXTEND},
        )
        await connection.execute(text(_CLEANUP_TASKS_EXTEND_SQL))
        await connection.execute(
            text(
                "INSERT INTO unidata_schema_migrations (version) VALUES (:version) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": MIGRATION_VERSION_CLEANUP_TASKS_REGIONS},
        )
        await ensure_collection_settings_rls(connection)
        await connection.execute(
            text(
                "INSERT INTO unidata_schema_migrations (version) VALUES (:version) "
                "ON CONFLICT (version) DO NOTHING"
            ),
            {"version": MIGRATION_VERSION_COLLECTION_SETTINGS_RLS},
        )
        await apply_document_tenancy_migration(connection)
        await apply_physical_tenancy_migration(connection)


if __name__ == "__main__":
    asyncio.run(migrate())
    print(f"数据库迁移完成: {MIGRATION_VERSION}")

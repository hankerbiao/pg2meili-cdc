"""将通用文档表迁移为按开放平台应用隔离的存储模型。"""

import asyncio
import os
import sys

from sqlalchemy import text

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.database import engine  # noqa: E402
from app.models import Base  # noqa: E402


MIGRATION_VERSION = "20260730_document_tenancy"


async def apply_document_tenancy_migration(connection) -> bool:
    """应用文档租户迁移；已执行时返回 False。"""
    applied = await connection.scalar(
        text("SELECT 1 FROM unidata_schema_migrations WHERE version = :version"),
        {"version": MIGRATION_VERSION},
    )
    if applied:
        return False

    preparation_statements = (
        "ALTER TABLE uni_documents ADD COLUMN IF NOT EXISTS row_id UUID",
        "ALTER TABLE uni_documents ADD COLUMN IF NOT EXISTS app_id VARCHAR",
        "UPDATE uni_documents SET row_id = gen_random_uuid() WHERE row_id IS NULL",
        """
        UPDATE uni_documents
        SET app_name = COALESCE(NULLIF(BTRIM(app_name), ''), 'legacy')
        WHERE app_name IS NULL OR app_name != BTRIM(app_name) OR BTRIM(app_name) = ''
        """,
        """
        WITH tenant_names AS (
            SELECT DISTINCT app_name
            FROM uni_documents
        )
        INSERT INTO open_platform_apps (
            id, app_name, display_name, owner_itcode, description,
            status, version, created_at, updated_at
        )
        SELECT
            md5('unidata:migrated-app:' || tenant_names.app_name),
            tenant_names.app_name,
            tenant_names.app_name,
            'migration',
            '由文档租户迁移自动创建',
            'active',
            1,
            NOW(),
            NOW()
        FROM tenant_names
        ON CONFLICT (app_name) DO NOTHING
        """,
        """
        UPDATE uni_documents AS document
        SET app_id = application.id
        FROM open_platform_apps AS application
        WHERE document.app_name = application.app_name
          AND document.app_id IS NULL
        """,
    )

    for statement in preparation_statements:
        await connection.execute(text(statement))

    unresolved = await connection.scalar(
        text("SELECT COUNT(*) FROM uni_documents WHERE app_id IS NULL")
    )
    if unresolved:
        raise RuntimeError(f"仍有 {unresolved} 条文档无法映射到开放平台应用")

    constraint_statements = (
        "ALTER TABLE uni_documents ALTER COLUMN row_id SET DEFAULT gen_random_uuid()",
        "ALTER TABLE uni_documents ALTER COLUMN row_id SET NOT NULL",
        "ALTER TABLE uni_documents ALTER COLUMN app_id SET NOT NULL",
        "ALTER TABLE uni_documents ALTER COLUMN app_name SET NOT NULL",
        """
        DO $$
        DECLARE
            primary_key_name TEXT;
            primary_key_columns TEXT[];
        BEGIN
            SELECT constraint_info.conname, constraint_info.columns
            INTO primary_key_name, primary_key_columns
            FROM (
                SELECT
                    constraint_row.conname,
                    ARRAY_AGG(attribute.attname ORDER BY key_column.ordinality) AS columns
                FROM pg_constraint AS constraint_row
                JOIN LATERAL UNNEST(constraint_row.conkey)
                    WITH ORDINALITY AS key_column(attnum, ordinality) ON TRUE
                JOIN pg_attribute AS attribute
                    ON attribute.attrelid = constraint_row.conrelid
                   AND attribute.attnum = key_column.attnum
                WHERE constraint_row.conrelid = 'uni_documents'::regclass
                  AND constraint_row.contype = 'p'
                GROUP BY constraint_row.conname
            ) AS constraint_info;

            IF primary_key_columns IS DISTINCT FROM ARRAY['row_id']::TEXT[] THEN
                IF primary_key_name IS NOT NULL THEN
                    EXECUTE FORMAT(
                        'ALTER TABLE uni_documents DROP CONSTRAINT %I',
                        primary_key_name
                    );
                END IF;
                ALTER TABLE uni_documents
                    ADD CONSTRAINT pk_uni_documents_row_id PRIMARY KEY (row_id);
            END IF;
        END $$
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'uni_documents'::regclass
                  AND conname = 'uq_uni_documents_app_collection_id'
            ) THEN
                ALTER TABLE uni_documents
                    ADD CONSTRAINT uq_uni_documents_app_collection_id
                    UNIQUE (app_id, collection, id);
            END IF;
        END $$
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint AS constraint_row
                JOIN pg_attribute AS attribute
                    ON attribute.attrelid = constraint_row.conrelid
                   AND attribute.attnum = ANY(constraint_row.conkey)
                WHERE constraint_row.conrelid = 'uni_documents'::regclass
                  AND constraint_row.contype = 'f'
                  AND attribute.attname = 'app_id'
            ) THEN
                ALTER TABLE uni_documents
                    ADD CONSTRAINT fk_uni_documents_app_id
                    FOREIGN KEY (app_id) REFERENCES open_platform_apps(id)
                    ON DELETE RESTRICT;
            END IF;
        END $$
        """,
        "CREATE INDEX IF NOT EXISTS ix_uni_documents_app_id ON uni_documents (app_id)",
        """
        CREATE INDEX IF NOT EXISTS ix_uni_documents_app_collection
        ON uni_documents (app_id, collection)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_uni_documents_routing
        ON uni_documents (app_name, collection)
        """,
        "ALTER TABLE uni_documents REPLICA IDENTITY FULL",
    )

    for statement in constraint_statements:
        await connection.execute(text(statement))

    await connection.execute(
        text(
            "INSERT INTO unidata_schema_migrations (version) VALUES (:version)"
        ),
        {"version": MIGRATION_VERSION},
    )
    return True


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
        await apply_document_tenancy_migration(connection)


if __name__ == "__main__":
    asyncio.run(migrate())
    print(f"数据库迁移完成: {MIGRATION_VERSION}")

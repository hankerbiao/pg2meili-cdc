"""需要 PostgreSQL 的文档租户隔离回归测试。"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpenPlatformApp
from app.repositories.document_repository import document_repository
from migrations.migrate_document_tenancy import apply_document_tenancy_migration


async def test_apps_can_reuse_document_id_without_cross_tenant_access(
    db_session: AsyncSession,
):
    suffix = uuid.uuid4().hex[:12]
    app_a_id = f"app-a-{suffix}"
    app_b_id = f"app-b-{suffix}"
    app_a_name = f"tenant-a-{suffix}"
    app_b_name = f"tenant-b-{suffix}"
    db_session.add_all(
        [
            OpenPlatformApp(
                id=app_a_id,
                app_name=app_a_name,
                display_name="Tenant A",
                owner_itcode="pytest",
                status="active",
                version=1,
            ),
            OpenPlatformApp(
                id=app_b_id,
                app_name=app_b_name,
                display_name="Tenant B",
                owner_itcode="pytest",
                status="active",
                version=1,
            ),
        ]
    )
    await db_session.flush()

    await document_repository.upsert_documents(
        db_session,
        app_id=app_a_id,
        app_name=app_a_name,
        collection="shared",
        items=[("same-id", {"id": "same-id", "owner": "A"})],
    )
    await document_repository.upsert_documents(
        db_session,
        app_id=app_b_id,
        app_name=app_b_name,
        collection="shared",
        items=[("same-id", {"id": "same-id", "owner": "B"})],
    )

    document_a = await document_repository.get_document(
        db_session, app_a_id, "shared", "same-id"
    )
    document_b = await document_repository.get_document(
        db_session, app_b_id, "shared", "same-id"
    )
    assert document_a is not None and document_a.payload["owner"] == "A"
    assert document_b is not None and document_b.payload["owner"] == "B"

    assert await document_repository.soft_delete_document(
        db_session, app_a_id, "shared", "same-id"
    )
    assert (
        await document_repository.get_document(
            db_session, app_a_id, "shared", "same-id"
        )
        is None
    )
    assert (
        await document_repository.get_document(
            db_session, app_b_id, "shared", "same-id"
        )
        is not None
    )


async def test_legacy_document_table_is_backfilled_before_constraints(
    db_session: AsyncSession,
):
    schema = f"tenant_migration_{uuid.uuid4().hex[:12]}"
    await db_session.execute(text(f'CREATE SCHEMA "{schema}"'))
    await db_session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
    setup_statements = (
        """
        CREATE TABLE unidata_schema_migrations (
            version VARCHAR PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE open_platform_apps (
            id VARCHAR PRIMARY KEY,
            app_name VARCHAR NOT NULL UNIQUE,
            display_name VARCHAR NOT NULL,
            owner_itcode VARCHAR NOT NULL,
            description TEXT,
            status VARCHAR NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """,
        """
        CREATE TABLE uni_documents (
            id VARCHAR PRIMARY KEY,
            collection VARCHAR NOT NULL,
            app_name VARCHAR,
            payload JSONB,
            is_delete BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """,
        """
        INSERT INTO uni_documents (id, collection, app_name, payload)
        VALUES
            ('legacy-a', 'items', 'orders', '{"id":"legacy-a"}'),
            ('legacy-b', 'items', NULL, '{"id":"legacy-b"}')
        """,
    )
    for statement in setup_statements:
        await db_session.execute(text(statement))

    connection = await db_session.connection()
    assert await apply_document_tenancy_migration(connection) is True

    rows = (
        await db_session.execute(
            text(
                "SELECT id, app_name, app_id, row_id "
                "FROM uni_documents ORDER BY id"
            )
        )
    ).all()
    assert len(rows) == 2
    assert rows[0].app_name == "orders"
    assert rows[1].app_name == "legacy"
    assert all(row.app_id and row.row_id for row in rows)

    primary_key_columns = (
        await db_session.execute(
            text("""
            SELECT ARRAY_AGG(attribute.attname ORDER BY key_column.ordinality)
            FROM pg_constraint AS constraint_row
            JOIN LATERAL UNNEST(constraint_row.conkey)
                WITH ORDINALITY AS key_column(attnum, ordinality) ON TRUE
            JOIN pg_attribute AS attribute
                ON attribute.attrelid = constraint_row.conrelid
               AND attribute.attnum = key_column.attnum
            WHERE constraint_row.conrelid = 'uni_documents'::regclass
              AND constraint_row.contype = 'p'
            """)
        )
    ).scalar_one()
    assert primary_key_columns == ["row_id"]

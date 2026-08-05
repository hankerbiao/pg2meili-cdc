"""将旧 public.uni_documents 拆分到按 app_id 命名的租户 schema。"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.database import engine  # noqa: E402
from app.core.tenant import tenant_schema  # noqa: E402
from app.services.tenant_service import ensure_search_outbox, provision_tenant  # noqa: E402

MIGRATION_VERSION = "20260805_physical_tenancy"


def _safe_schema(app_id: str) -> str:
    schema = tenant_schema(app_id)
    if not schema.startswith("tenant_") or any(ch not in "0123456789abcdefghijklmnopqrstuvwxyz_" for ch in schema):
        raise ValueError("非法租户 schema")
    return schema


async def apply_physical_tenancy_migration(connection) -> bool:
    applied = await connection.scalar(
        text("SELECT 1 FROM unidata_schema_migrations WHERE version = :version"),
        {"version": MIGRATION_VERSION},
    )
    if applied:
        return False

    await ensure_search_outbox(connection)
    app_ids = (
        await connection.execute(
            text(
                "SELECT DISTINCT app_id FROM public.uni_documents "
                "WHERE app_id IS NOT NULL ORDER BY app_id"
            )
        )
    ).scalars().all()

    for app_id in app_ids:
        if not app_id:
            raise RuntimeError("旧文档存在空 app_id，无法安全迁移")
        app_exists = await connection.scalar(
            text("SELECT 1 FROM public.open_platform_apps WHERE id = :app_id"),
            {"app_id": app_id},
        )
        if not app_exists:
            raise RuntimeError(f"文档 app_id 不存在对应应用: {app_id}")
        schema = _safe_schema(app_id)
        await provision_tenant(connection, app_id)
        await connection.execute(
            text("SELECT set_config('app.tenant_id', :app_id, true)"),
            {"app_id": app_id},
        )
        await connection.execute(
            text(
                f'''
                INSERT INTO "{schema}".uni_documents
                    (row_id, id, app_id, collection, app_name, payload, is_delete, created_at, updated_at)
                SELECT row_id, id, app_id, collection, app_name, payload, is_delete, created_at, updated_at
                FROM public.uni_documents
                WHERE app_id = :app_id
                ON CONFLICT (app_id, collection, id) DO UPDATE SET
                    app_name = EXCLUDED.app_name,
                    payload = EXCLUDED.payload,
                    is_delete = EXCLUDED.is_delete,
                    updated_at = EXCLUDED.updated_at
                '''
            ),
            {"app_id": app_id},
        )
        source_count = await connection.scalar(
            text("SELECT count(*) FROM public.uni_documents WHERE app_id = :app_id"),
            {"app_id": app_id},
        )
        target_count = await connection.scalar(
            text(f'SELECT count(*) FROM "{schema}".uni_documents')
        )
        source_pairs = await connection.scalar(
            text(
                "SELECT count(DISTINCT (collection, id)) "
                "FROM public.uni_documents WHERE app_id = :app_id"
            ),
            {"app_id": app_id},
        )
        target_pairs = await connection.scalar(
            text(
                f'SELECT count(DISTINCT (collection, id)) FROM "{schema}".uni_documents'
            )
        )
        source_deleted = await connection.scalar(
            text(
                "SELECT count(*) FROM public.uni_documents "
                "WHERE app_id = :app_id AND is_delete"
            ),
            {"app_id": app_id},
        )
        target_deleted = await connection.scalar(
            text(f'SELECT count(*) FROM "{schema}".uni_documents WHERE is_delete')
        )
        if (source_count, source_pairs, source_deleted) != (
            target_count,
            target_pairs,
            target_deleted,
        ):
            raise RuntimeError(
                f"租户迁移校验失败 app_id={app_id} "
                f"source=({source_count}, {source_pairs}, {source_deleted}) "
                f"target=({target_count}, {target_pairs}, {target_deleted})"
            )
        print(f"租户迁移校验通过 app_id={app_id} rows={target_count} pairs={target_pairs}")

    await connection.execute(
        text(
            "INSERT INTO unidata_schema_migrations (version) VALUES (:version) "
            "ON CONFLICT (version) DO NOTHING"
        ),
        {"version": MIGRATION_VERSION},
    )
    return True


async def migrate() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS unidata_schema_migrations (
                    version VARCHAR PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await apply_physical_tenancy_migration(connection)


if __name__ == "__main__":
    asyncio.run(migrate())
    print(f"数据库迁移完成: {MIGRATION_VERSION}")

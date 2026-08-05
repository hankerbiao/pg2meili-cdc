"""租户命名、RLS 上下文和 schema 初始化的单元测试。"""

from unittest.mock import AsyncMock

import pytest

from app.core.tenant import index_uid, set_tenant_context, tenant_schema, tenant_schema_map
from migrations.migrate_physical_tenancy import apply_physical_tenancy_migration
from app.services.tenant_service import provision_tenant


def test_tenant_names_are_stable_and_app_scoped():
    assert tenant_schema("app-a") == tenant_schema("app-a")
    assert tenant_schema("app-a") != tenant_schema("app-b")
    assert tenant_schema("app-a").startswith("tenant_")
    assert index_uid("app-a", "items") == index_uid("app-a", "items")
    assert index_uid("app-a", "items") != index_uid("app-b", "items")
    assert index_uid("app-a", "items").startswith("t_")


def test_index_uid_rejects_invalid_collection():
    for collection in ("", "../items", "items with space", "a" * 129):
        with pytest.raises(ValueError):
            index_uid("app-a", collection)


def test_tenant_schema_map_targets_tenant_schema():
    assert tenant_schema_map("app-a") == {None: tenant_schema("app-a")}


async def test_set_tenant_context_sets_transaction_locals():
    db = AsyncMock()
    db.info = {}

    await set_tenant_context(db, "app-a")

    statements = [call.args[0].text for call in db.execute.await_args_list]
    assert any("set_config('app.tenant_id'" in statement for statement in statements)
    assert any("SET LOCAL search_path" in statement for statement in statements)
    assert db.info["unidata.tenant_id"] == "app-a"


async def test_provision_tenant_creates_rls_and_trigger():
    db = AsyncMock()
    await provision_tenant(db, "app-a")

    statements = " ".join(
        call.args[0].text for call in db.execute.await_args_list
    )
    assert 'CREATE SCHEMA IF NOT EXISTS "tenant_' in statements
    assert "ENABLE ROW LEVEL SECURITY" in statements
    assert "FORCE ROW LEVEL SECURITY" in statements
    assert "tenant_isolation" in statements
    assert "CREATE TRIGGER emit_search_outbox" in statements
    assert "CREATE TABLE IF NOT EXISTS public.search_outbox" in statements


async def test_physical_tenancy_migration_is_idempotent():
    connection = AsyncMock()
    connection.scalar.return_value = 1

    assert await apply_physical_tenancy_migration(connection) is False

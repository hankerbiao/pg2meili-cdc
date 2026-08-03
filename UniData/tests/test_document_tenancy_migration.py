"""文档租户迁移的编排测试。"""

from unittest.mock import AsyncMock

from migrations.migrate_document_tenancy import apply_document_tenancy_migration


async def test_document_tenancy_migration_builds_required_constraints():
    connection = AsyncMock()
    connection.scalar.side_effect = [None, 0]

    applied = await apply_document_tenancy_migration(connection)

    statements = "\n".join(
        str(call.args[0]) for call in connection.execute.await_args_list
    )
    assert applied is True
    assert "ADD COLUMN IF NOT EXISTS row_id UUID" in statements
    assert "ADD COLUMN IF NOT EXISTS app_id VARCHAR" in statements
    assert "PRIMARY KEY (row_id)" in statements
    assert "UNIQUE (app_id, collection, id)" in statements
    assert "FOREIGN KEY (app_id)" in statements
    assert "REPLICA IDENTITY FULL" in statements
    assert connection.execute.await_args_list[-1].args[1]["version"] == (
        "20260730_document_tenancy"
    )


async def test_document_tenancy_migration_is_idempotent():
    connection = AsyncMock()
    connection.scalar.return_value = 1

    applied = await apply_document_tenancy_migration(connection)

    assert applied is False
    connection.execute.assert_not_awaited()

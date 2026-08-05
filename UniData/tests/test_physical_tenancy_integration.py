"""需要真实 PostgreSQL 的租户物理隔离集成测试。"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.tenant import set_tenant_context, tenant_schema
from app.models import OpenPlatformApp
from app.models.open_platform import ApiKey, OpenPlatformAuditLog
from app.repositories.document_repository import document_repository
from app.services.open_platform_service import OpenPlatformService
from app.services.tenant_service import provision_tenant, tenant_exists


async def _add_app(db: AsyncSession, prefix: str) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:12]
    app_id = f"{prefix}-{suffix}"
    app_name = f"{prefix}-name-{suffix}"
    db.add(
        OpenPlatformApp(
            id=app_id,
            app_name=app_name,
            display_name=f"{prefix} display",
            owner_itcode="pytest",
        )
    )
    await db.flush()
    return app_id, app_name


async def test_trigger_emits_outbox_events_and_rolls_back_atomically(
    db_session: AsyncSession,
):
    app_id, app_name = await _add_app(db_session, "trigger-app")
    await document_repository.upsert_documents(
        db_session,
        app_id=app_id,
        app_name=app_name,
        collection="items",
        items=[("doc-1", {"id": "doc-1", "name": "one"})],
    )

    events = (
        await db_session.execute(
            text(
                "SELECT operation, app_id, collection, document_id, document, event_version "
                "FROM public.search_outbox WHERE app_id = :app_id ORDER BY event_version"
            ),
            {"app_id": app_id},
        )
    ).all()
    assert len(events) == 1
    assert events[0].operation == "upsert"
    assert events[0].collection == "items"
    assert events[0].document_id == "doc-1"
    assert events[0].document["id"] == "doc-1"
    assert events[0].event_version is not None

    assert await document_repository.soft_delete_document(
        db_session, app_id, "items", "doc-1"
    )
    events = (
        await db_session.execute(
            text(
                "SELECT operation, document FROM public.search_outbox "
                "WHERE app_id = :app_id ORDER BY event_version"
            ),
            {"app_id": app_id},
        )
    ).all()
    assert [event.operation for event in events] == ["upsert", "delete"]
    assert events[1].document is None

    schema = tenant_schema(app_id)
    await set_tenant_context(db_session, app_id)
    await db_session.execute(
        text(f'DELETE FROM "{schema}".uni_documents WHERE id = :id'),
        {"id": "doc-1"},
    )
    count = (
        await db_session.scalar(
            text("SELECT count(*) FROM public.search_outbox WHERE app_id = :app_id"),
            {"app_id": app_id},
        )
    )
    assert count == 3

    before = count
    nested = await db_session.begin_nested()
    await document_repository.upsert_documents(
        db_session,
        app_id=app_id,
        app_name=app_name,
        collection="items",
        items=[("rollback-doc", {"id": "rollback-doc"})],
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM public.search_outbox WHERE app_id = :app_id"),
            {"app_id": app_id},
        )
        == before + 1
    )
    await nested.rollback()
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM public.search_outbox WHERE app_id = :app_id"),
            {"app_id": app_id},
        )
        == before
    )


async def test_rls_blocks_cross_tenant_direct_access(db_session: AsyncSession):
    app_a_id, app_a_name = await _add_app(db_session, "rls-a")
    app_b_id, app_b_name = await _add_app(db_session, "rls-b")
    await document_repository.upsert_documents(
        db_session,
        app_id=app_a_id,
        app_name=app_a_name,
        collection="shared",
        items=[("same-id", {"owner": "A"})],
    )
    await document_repository.upsert_documents(
        db_session,
        app_id=app_b_id,
        app_name=app_b_name,
        collection="shared",
        items=[("same-id", {"owner": "B"})],
    )

    schema_a = tenant_schema(app_a_id)
    schema_b = tenant_schema(app_b_id)
    database = await db_session.scalar(text("SELECT current_database()"))
    role = f"rls_{uuid.uuid4().hex[:12]}"
    limited_role = f"rls_limited_{uuid.uuid4().hex[:12]}"
    password = uuid.uuid4().hex
    await db_session.execute(text(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\''))
    await db_session.execute(text(f'CREATE ROLE "{limited_role}" LOGIN PASSWORD \'{password}\''))
    await db_session.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO "{role}", "{limited_role}"'))
    await db_session.execute(
        text(
            f'GRANT USAGE ON SCHEMA "{schema_a}", "{schema_b}" TO "{role}"'
        )
    )
    await db_session.execute(
        text(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{schema_a}".uni_documents, "{schema_b}".uni_documents TO "{role}"'
        )
    )
    await db_session.execute(
        text(f'GRANT USAGE ON SCHEMA "{schema_b}" TO "{limited_role}"')
    )
    await db_session.execute(
        text(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{schema_b}".uni_documents TO "{limited_role}"'
        )
    )
    await db_session.execute(
        text(f'GRANT USAGE ON SCHEMA public TO "{role}", "{limited_role}"')
    )
    await db_session.commit()

    engine = create_async_engine(
        f"postgresql+asyncpg://{role}:{password}@127.0.0.1:5432/{database}",
        poolclass=NullPool,
    )
    limited_engine = create_async_engine(
        f"postgresql+asyncpg://{limited_role}:{password}@127.0.0.1:5432/{database}",
        poolclass=NullPool,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :app_id, true)"),
                {"app_id": app_b_id},
            )
            rows = (
                await conn.execute(text(f'SELECT id FROM "{schema_a}".uni_documents'))
            ).scalars().all()
            assert rows == []
            result = await conn.execute(
                text(
                    f'UPDATE "{schema_a}".uni_documents SET updated_at = NOW() '
                    "WHERE app_id = :app_id AND id = :id"
                ),
                {"app_id": app_a_id, "id": "same-id"},
            )
            assert result.rowcount == 0
            with pytest.raises(Exception):
                await conn.execute(
                    text(
                        f'INSERT INTO "{schema_a}".uni_documents '
                        "(row_id, id, app_id, collection, app_name, payload) "
                        "VALUES (gen_random_uuid(), :id, :app_id, 'shared', 'a', '{}'::jsonb)"
                    ),
                    {"id": "forbidden", "app_id": app_a_id},
                )

        async with limited_engine.begin() as conn:
            with pytest.raises(Exception):
                await conn.execute(
                    text(f'SELECT id FROM "{schema_a}".uni_documents')
                )
    finally:
        await engine.dispose()
        await limited_engine.dispose()
        await db_session.execute(text(f'DROP OWNED BY "{role}", "{limited_role}"'))
        await db_session.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        await db_session.execute(text(f'DROP ROLE IF EXISTS "{limited_role}"'))
        await db_session.commit()


async def test_tenant_provisioning_is_idempotent_and_rolls_back(
    db_session: AsyncSession,
):
    app_id, _ = await _add_app(db_session, "provision-app")
    await provision_tenant(db_session, app_id)
    schema = tenant_schema(app_id)
    assert await tenant_exists(db_session, app_id)
    await provision_tenant(db_session, app_id)
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM pg_namespace WHERE nspname = :schema"),
            {"schema": schema},
        )
        == 1
    )

    second_id = f"provision-rollback-{uuid.uuid4().hex[:12]}"
    with pytest.raises(RuntimeError):
        async with db_session.begin_nested():
            db_session.add(
                OpenPlatformApp(
                    id=second_id,
                    app_name=f"provision-rollback-name-{uuid.uuid4().hex[:12]}",
                    display_name="Rollback",
                    owner_itcode="pytest",
                )
            )
            await db_session.flush()
            await provision_tenant(db_session, second_id)
            raise RuntimeError("force rollback")
    assert not await tenant_exists(db_session, second_id)
    assert await db_session.get(OpenPlatformApp, second_id) is None


async def test_connection_reuse_does_not_leak_tenant_context(
    db_session: AsyncSession,
):
    app_a_id, app_a_name = await _add_app(db_session, "reuse-a")
    app_b_id, app_b_name = await _add_app(db_session, "reuse-b")
    await document_repository.upsert_documents(
        db_session,
        app_id=app_a_id,
        app_name=app_a_name,
        collection="items",
        items=[("doc-a", {"owner": "A"})],
    )
    await db_session.commit()

    await document_repository.upsert_documents(
        db_session,
        app_id=app_b_id,
        app_name=app_b_name,
        collection="items",
        items=[("doc-b", {"owner": "B"})],
    )
    await db_session.commit()

    assert (
        await db_session.scalar(
            text("SELECT current_setting('app.tenant_id', true)")
        )
        is None
    )
    document_a = await document_repository.get_document(
        db_session, app_a_id, "items", "doc-a"
    )
    document_b = await document_repository.get_document(
        db_session, app_b_id, "items", "doc-b"
    )
    assert document_a is not None and document_a.payload["owner"] == "A"
    assert document_b is not None and document_b.payload["owner"] == "B"


async def test_delete_app_revokes_keys_and_drops_schema(db_session: AsyncSession):
    app_id, app_name = await _add_app(db_session, "delete-app")
    await document_repository.upsert_documents(
        db_session,
        app_id=app_id,
        app_name=app_name,
        collection="items",
        items=[("doc-1", {"id": "doc-1"})],
    )
    db_session.add(
        ApiKey(
            id=f"ak_{uuid.uuid4().hex[:16]}",
            app_id=app_id,
            name="delete-test",
            secret_hash="0" * 64,
            last_four="abcd",
            scopes=["search:read"],
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            version=1,
        )
    )
    await db_session.flush()

    deleted = await OpenPlatformService.delete_app(
        db_session,
        app_id=app_id,
        actor="admin",
        source_ip="127.0.0.1",
    )
    assert deleted.status == "deleted"
    assert not await tenant_exists(db_session, app_id)
    await db_session.flush()
    keys = await OpenPlatformService.list_keys(db_session, app_id)
    assert keys and all(key.status == "revoked" for key in keys)
    audit = await db_session.scalar(
        select(OpenPlatformAuditLog).where(
            OpenPlatformAuditLog.app_id == app_id,
            OpenPlatformAuditLog.action == "app.delete",
        )
    )
    assert audit is not None and audit.details == {"collections": ["items"]}

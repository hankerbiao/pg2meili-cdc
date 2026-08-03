"""文档租户隔离的结构与 SQL 契约测试。"""

from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from app.models.document import Document
from app.repositories.document_repository import document_repository


class FakeResult:
    rowcount = 1

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []


def normalized_sql(statement) -> str:
    compiled = statement.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).split())


def test_document_uses_internal_primary_key_and_tenant_unique_constraint():
    primary_key = [column.name for column in Document.__table__.primary_key.columns]
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in Document.__table__.constraints
        if constraint.name
    }

    assert primary_key == ["row_id"]
    assert unique_constraints["uq_uni_documents_app_collection_id"] == (
        "app_id",
        "collection",
        "id",
    )


async def test_upsert_uses_tenant_scoped_conflict_target():
    db = AsyncMock()
    db.execute.return_value = FakeResult()

    await document_repository.upsert_documents(
        db=db,
        app_id="app-a",
        app_name="orders",
        collection="items",
        items=[("same-id", {"id": "same-id", "name": "A"})],
    )

    statement = db.execute.await_args.args[0]
    sql = normalized_sql(statement)
    assert "ON CONFLICT (app_id, collection, id) DO UPDATE" in sql
    assert "app_id_m0" in statement.compile(dialect=postgresql.dialect()).params
    assert statement.compile(dialect=postgresql.dialect()).params["app_id_m0"] == "app-a"


async def test_read_and_delete_queries_are_tenant_scoped():
    db = AsyncMock()
    db.execute.return_value = FakeResult()

    await document_repository.get_document(db, "app-a", "items", "same-id")
    await document_repository.soft_delete_document(db, "app-a", "items", "same-id")
    await document_repository.list_documents(db, "app-a", "items", limit=20, offset=0)
    await document_repository.list_collections_by_app(db, "app-a", limit=100, offset=0)
    await document_repository.soft_delete_collection_for_app(db, "app-a", "items")

    assert db.execute.await_count == 5
    for call in db.execute.await_args_list:
        assert "uni_documents.app_id" in normalized_sql(call.args[0])

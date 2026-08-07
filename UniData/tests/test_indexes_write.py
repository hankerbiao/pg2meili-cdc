"""索引写操作回归测试（此前仅 GET /indexes 有覆盖）。

覆盖此前零测试的：
- ``DELETE /indexes/{collection}`` 删除索引并逻辑删除集合内文档；
- ``POST /indexes/{collection}/settings`` 设置可过滤/可排序字段（经 Kafka 下发）。

鉴权复用真实 API Key（data:write 作用域）；delete_collection_for_app /
update_index_settings_async 的副作用走测试库与 mock 的 KafkaManager，不触达真实 Meilisearch。

需要真实 Postgres：通过 ``TEST_PG_CONN_STRING`` 提供隔离测试库；
未配置时 conftest 的 db_session 会自动 skip 本模块所有用例。
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.main import app
from app.services.open_platform_service import open_platform_service, utc_now


@pytest.fixture
async def index_client(db_session: AsyncSession):
    """仅覆盖 get_db，使用真实 API Key 鉴权（不覆盖 get_current_app）。"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def write_key(db_session: AsyncSession, index_client: AsyncClient):
    """在 test-app-id 下签发 data:write 密钥（仅 flush 不提交）。"""
    key, plaintext = await open_platform_service.create_key(
        db_session,
        app_id="test-app-id",
        name="index-test-key",
        scopes=["data:read", "data:write"],
        expires_at=utc_now() + timedelta(days=90),
        actor="test",
        source_ip=None,
    )
    return plaintext


class TestIndexDelete:
    async def test_delete_index_requires_write_scope(self, index_client: AsyncClient, db_session: AsyncSession):
        # 仅 data:read 的密钥 -> 403
        ro_key, plaintext = await open_platform_service.create_key(
            db_session, app_id="test-app-id", name="ro", scopes=["data:read"],
            expires_at=utc_now() + timedelta(days=90), actor="test", source_ip=None,
        )
        resp = await index_client.delete(
            "/api/v1/indexes/products",
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 403

    async def test_delete_index_logically_deletes_documents(
        self, index_client: AsyncClient, db_session: AsyncSession, write_key: str
    ):
        auth = {"Authorization": f"Bearer {write_key}"}
        # 先写入文档，再删除集合
        await index_client.post(
            "/api/v1/data/products",
            headers=auth,
            json={"id": "idx-1", "name": "n"},
        )
        with patch("app.services.index_service.get_kafka_manager") as gkm:
            gkm.return_value = _null_kafka()
            resp = await index_client.delete("/api/v1/indexes/products", headers=auth)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["collection"] == "products"
        assert resp.json()["data"]["deleted_count"] >= 1


class TestIndexSettings:
    async def test_update_settings_requires_write_scope(self, index_client: AsyncClient, db_session: AsyncSession):
        ro_key, plaintext = await open_platform_service.create_key(
            db_session, app_id="test-app-id", name="ro2", scopes=["data:read"],
            expires_at=utc_now() + timedelta(days=90), actor="test", source_ip=None,
        )
        resp = await index_client.post(
            "/api/v1/indexes/products/settings",
            headers={"Authorization": f"Bearer {plaintext}"},
            json={"filterableAttributes": ["name"], "sortableAttributes": ["price"]},
        )
        assert resp.status_code == 403

    async def test_update_settings_returns_index_uid(
        self, index_client: AsyncClient, db_session: AsyncSession, write_key: str
    ):
        auth = {"Authorization": f"Bearer {write_key}"}
        with patch("app.services.index_service.get_kafka_manager") as gkm:
            gkm.return_value = _null_kafka()
            resp = await index_client.post(
                "/api/v1/indexes/products/settings",
                headers=auth,
                json={"filterableAttributes": ["name"], "sortableAttributes": ["price"]},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["collection"] == "products"
        assert data["index_uid"]


def _null_kafka():
    """返回无操作的 KafkaManager 替身，避免触达真实 Meilisearch。"""

    class _Null:
        def send(self, *a, **k):
            return None

        def send_json(self, *a, **k):
            return None

        def flush(self):
            return None

        def close(self):
            return None

    return _Null()

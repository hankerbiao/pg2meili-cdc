"""Opt-in SDK tests against the local Docker stack.

These tests intentionally verify the real CDC route instead of inserting documents
into Meilisearch: SDK -> UniData -> PostgreSQL outbox -> Debezium -> Kafka ->
meilisearch-sync -> Agent search API. Enable them with MELIDATA_LOCAL_STACK=1.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

import httpx
import pytest

from melidata_sdk import (
    AsyncMeliDataClient,
    MeliDataClient,
    PermissionDeniedError,
)


pytestmark = pytest.mark.integration


ROOT = Path(__file__).resolve().parents[2]
PROVISION_SCRIPT = ROOT / "UniData/scripts/provision_sdk_integration_tenant.py"
BASE_URL = os.environ.get("MELIDATA_BASE_URL", "http://127.0.0.1:8080")
SEARCH_URL = os.environ.get("MELIDATA_SEARCH_URL", "http://127.0.0.1:8091")
CONNECT_URL = os.environ.get("MELIDATA_CONNECT_URL", "http://127.0.0.1:8083")
POLL_TIMEOUT_SECONDS = float(os.environ.get("MELIDATA_CDC_TIMEOUT", "30"))

T = TypeVar("T")


@dataclass(frozen=True)
class LocalTenant:
    app_id: str
    app_name: str
    full_key: str
    data_key: str
    search_key: str

    def collection(self, label: str) -> str:
        return f"sdk_it_{label}_{uuid.uuid4().hex[:8]}"


def _require_local_stack() -> None:
    if os.environ.get("MELIDATA_LOCAL_STACK") != "1":
        pytest.skip("set MELIDATA_LOCAL_STACK=1 to run local stack integration tests")


def _get_json(url: str) -> dict[str, object]:
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    return response.json()


def _wait_for(description: str, assertion: Callable[[], T]) -> T:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return assertion()
        except Exception as exc:  # The CDC pipeline is eventually consistent.
            last_error = exc
            time.sleep(0.5)
    raise AssertionError(f"timed out waiting for {description}: {last_error}") from last_error


def _assert_stack_ready() -> None:
    assert _get_json(f"{BASE_URL}/ready")["data"]["status"] == "ready"
    assert _get_json(f"{SEARCH_URL}/health")["status"] == "healthy"
    assert _get_json("http://127.0.0.1:7700/health")["status"] == "available"

    connector = _get_json(f"{CONNECT_URL}/connectors/pg-search-outbox-connector/status")
    assert connector["connector"]["state"] == "RUNNING"
    assert connector["tasks"] and all(
        task["state"] == "RUNNING" for task in connector["tasks"]
    )


def _provision_tenant() -> LocalTenant:
    app_name = f"sdk-it-{uuid.uuid4().hex[:12]}"
    command = [
        "docker",
        "compose",
        "-f",
        str(ROOT / "docker-compose.yml"),
        "exec",
        "-T",
        "unidata",
        "python",
        "-",
        app_name,
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        input=PROVISION_SCRIPT.read_text(encoding="utf-8"),
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    return LocalTenant(
        app_id=payload["app_id"],
        app_name=payload["app_name"],
        full_key=payload["keys"]["full"],
        data_key=payload["keys"]["data"],
        search_key=payload["keys"]["search"],
    )


def _assert_agent_accepts_key(api_key: str) -> None:
    response = httpx.post(
        f"{SEARCH_URL}/api/v1/collections/sdk_it_key_probe/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"q": "key-probe"},
        timeout=5.0,
    )
    assert response.status_code not in {401, 403}, response.text


@pytest.fixture(scope="module")
def tenant() -> LocalTenant:
    _require_local_stack()
    _assert_stack_ready()
    provisioned = _provision_tenant()
    _wait_for(
        "the test tenant's full-scope key to reach the Agent credential registry",
        lambda: _assert_agent_accepts_key(provisioned.full_key),
    )
    return provisioned


def _discovery_client(tenant: LocalTenant) -> MeliDataClient:
    return MeliDataClient(BASE_URL, tenant.full_key, region="local", timeout=5.0)


def _assert_search_has_id(client: MeliDataClient, collection: str, document_id: str) -> None:
    result = client.search(collection, query=document_id, limit=20)
    assert document_id in {str(hit.get("id")) for hit in result.hits}


def _assert_search_lacks_id(client: MeliDataClient, collection: str, document_id: str) -> None:
    result = client.search(collection, query=document_id, limit=20)
    assert document_id not in {str(hit.get("id")) for hit in result.hits}


def test_sync_client_crud_reaches_agent_through_cdc(tenant: LocalTenant) -> None:
    collection = tenant.collection("crud")
    document_id = f"doc-{uuid.uuid4().hex[:12]}"
    document = {
        "id": document_id,
        "title": "CDC SDK integration document",
        "status": "published",
    }

    with _discovery_client(tenant) as client:
        assert client.health()["status"] == "healthy"
        assert client.upsert_document(collection, document).id == document_id
        assert client.get_document(collection, document_id)["title"] == document["title"]
        assert [item["id"] for item in client.list_documents(collection)] == [document_id]
        assert collection in client.list_indexes()

        _wait_for("the CDC document to reach the discovered Agent", lambda: _assert_search_has_id(client, collection, document_id))

        assert client.delete_document(collection, document_id).id == document_id
        _wait_for("the CDC deletion to reach the discovered Agent", lambda: _assert_search_lacks_id(client, collection, document_id))


def test_sync_batch_upsert_and_pagination_reach_cdc(tenant: LocalTenant) -> None:
    collection = tenant.collection("batch")
    documents = [
        {"id": f"batch-{uuid.uuid4().hex[:10]}", "title": f"Batch item {number}"}
        for number in range(3)
    ]

    with _discovery_client(tenant) as client:
        result = client.upsert_documents(collection, documents)
        assert result.count == len(documents)
        assert set(result.ids) == {document["id"] for document in documents}

        first_page = client.list_documents(collection, limit=2, offset=0)
        second_page = client.list_documents(collection, limit=2, offset=2)
        assert {item["id"] for item in first_page + second_page} == {
            document["id"] for document in documents
        }

        for document in documents:
            _wait_for(
                f"batch document {document['id']} to reach the Agent through CDC",
                lambda document=document: _assert_search_has_id(client, collection, document["id"]),
            )


def test_index_settings_are_applied_by_the_agent(tenant: LocalTenant) -> None:
    collection = tenant.collection("settings")
    published_id = f"published-{uuid.uuid4().hex[:10]}"
    draft_id = f"draft-{uuid.uuid4().hex[:10]}"

    with _discovery_client(tenant) as client:
        client.upsert_documents(
            collection,
            [
                {"id": published_id, "title": "Settings published", "status": "published"},
                {"id": draft_id, "title": "Settings draft", "status": "draft"},
            ],
        )
        _wait_for("settings test documents to reach the Agent through CDC", lambda: _assert_search_has_id(client, collection, published_id))

        settings = client.update_index_settings(
            collection,
            filterable_attributes=["status"],
            sortable_attributes=["title"],
        )
        assert settings.collection == collection

        def assert_filter_works() -> None:
            result = client.search(collection, query="Settings", filter="status = published")
            ids = {str(hit.get("id")) for hit in result.hits}
            assert published_id in ids
            assert draft_id not in ids

        _wait_for("the asynchronous index settings command to be applied", assert_filter_works)


@pytest.mark.asyncio
async def test_async_client_upserts_and_searches_through_cdc(tenant: LocalTenant) -> None:
    collection = tenant.collection("async")
    document_id = f"async-{uuid.uuid4().hex[:12]}"

    async with AsyncMeliDataClient(BASE_URL, tenant.full_key, region="local", timeout=5.0) as client:
        assert (await client.upsert_document(collection, {"id": document_id, "title": "Async CDC document"})).id == document_id

        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                result = await client.search(collection, query=document_id)
                if document_id in {str(hit.get("id")) for hit in result.hits}:
                    return
                last_error = AssertionError("document not present in Agent result")
            except Exception as exc:  # CDC and Agent key snapshots are asynchronous.
                last_error = exc
            await asyncio.sleep(0.5)

        raise AssertionError(f"timed out waiting for async CDC search: {last_error}") from last_error


def test_scope_boundaries_are_enforced_by_control_plane_and_agent(tenant: LocalTenant) -> None:
    collection = tenant.collection("scopes")
    document_id = f"scope-{uuid.uuid4().hex[:12]}"

    with _discovery_client(tenant) as full_client:
        full_client.upsert_document(
            collection,
            {"id": document_id, "title": "Scope boundary document"},
        )
        _wait_for(
            "the scope test document to reach the Agent through CDC",
            lambda: _assert_search_has_id(full_client, collection, document_id),
        )

    with MeliDataClient(BASE_URL, tenant.search_key, search_url=SEARCH_URL, timeout=5.0) as search_client:
        def assert_search_key_is_accepted() -> None:
            result = search_client.search(collection, query=document_id)
            assert document_id in {str(hit.get("id")) for hit in result.hits}

        _wait_for("the search-only key to reach the Agent credential snapshot", assert_search_key_is_accepted)
        with pytest.raises(PermissionDeniedError):
            search_client.upsert_document(collection, {"id": "forbidden"})

    with MeliDataClient(BASE_URL, tenant.data_key, region="local", timeout=5.0) as data_client:
        with pytest.raises(PermissionDeniedError):
            data_client.search(collection, query="forbidden")

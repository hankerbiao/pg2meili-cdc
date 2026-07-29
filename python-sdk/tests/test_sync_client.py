from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from unidata_sdk import (
    ApiError,
    AsyncUniDataClient,
    AuthenticationError,
    NoSearchAgentError,
    PermissionDeniedError,
    ProtocolError,
    UniDataClient,
    ValidationError,
)


def response(status: int, payload: Any, request: httpx.Request) -> httpx.Response:
    return httpx.Response(status, json=payload, request=request)


def test_document_and_index_methods_use_control_api_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/health":
            return response(
                200, {"data": {"status": "healthy"}, "message": "ok"}, request
            )
        if (
            path in {"/api/v1/data/articles", "/api/v1/data/articles/batch"}
            and request.method == "POST"
        ):
            body = json.loads(request.content)
            if "items" in body:
                return response(
                    201,
                    {
                        "data": {
                            "status": "success",
                            "collection": "articles",
                            "count": 2,
                            "ids": ["a-1", "a-2"],
                        },
                        "message": "ok",
                    },
                    request,
                )
            return response(
                201,
                {
                    "data": {
                        "status": "success",
                        "id": body["id"],
                        "collection": "articles",
                    },
                    "message": "ok",
                },
                request,
            )
        if (
            request.url.raw_path == b"/api/v1/data/articles/b%2F1"
            and request.method == "GET"
        ):
            return response(
                200, {"data": {"id": "b/1", "title": "B"}, "message": "ok"}, request
            )
        if path == "/api/v1/data/articles" and request.method == "GET":
            assert dict(request.url.params) == {"limit": "10", "offset": "2"}
            return response(200, {"data": [{"id": "a-1"}], "message": "ok"}, request)
        if path == "/api/v1/data/articles/a-1" and request.method == "DELETE":
            return response(
                200,
                {
                    "data": {
                        "status": "success",
                        "id": "a-1",
                        "collection": "articles",
                    },
                    "message": "ok",
                },
                request,
            )
        if path == "/api/v1/indexes" and request.method == "GET":
            assert dict(request.url.params) == {"limit": "50", "offset": "1"}
            return response(200, {"data": ["articles"], "message": "ok"}, request)
        if path == "/api/v1/indexes/articles/settings":
            assert json.loads(request.content) == {
                "filterableAttributes": ["status"],
                "sortableAttributes": ["created_at"],
            }
            return response(
                200,
                {
                    "data": {
                        "status": "success",
                        "collection": "articles",
                        "index_uid": "demo_articles",
                    },
                    "message": "ok",
                },
                request,
            )
        if path == "/api/v1/indexes/articles" and request.method == "DELETE":
            return response(
                200,
                {
                    "data": {
                        "status": "success",
                        "collection": "articles",
                        "deleted_count": 3,
                    },
                    "message": "ok",
                },
                request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient(
        "https://control.test/", "secret-token", http_client=http_client
    )

    assert client.health() == {"status": "healthy"}
    assert client.upsert_document("articles", {"id": "a-1", "title": "A"}).id == "a-1"
    batch = client.upsert_documents("articles", [{"id": "a-1"}, {"id": "a-2"}])
    assert batch.count == 2
    assert client.get_document("articles", "b/1")["title"] == "B"
    assert client.list_documents("articles", limit=10, offset=2) == [{"id": "a-1"}]
    assert client.delete_document("articles", "a-1").status == "success"
    assert client.list_indexes(limit=50, offset=1) == ["articles"]
    settings = client.update_index_settings(
        "articles",
        filterable_attributes=["status"],
        sortable_attributes=["created_at"],
    )
    assert settings.index_uid == "demo_articles"
    assert client.delete_index("articles").deleted_count == 3

    assert all(
        request.headers["Authorization"] == "Bearer secret-token"
        for request in requests
    )
    assert all(
        request.headers["User-Agent"].startswith("unidata-sdk/") for request in requests
    )
    assert not any("/api/v1/index/indexes" in request.url.path for request in requests)

    client.close()
    assert not http_client.is_closed
    http_client.close()


def test_fixed_search_url_uses_versioned_contract_and_preserves_meta() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path == "/api/v1/collections/articles/search"
        assert json.loads(request.content) == {
            "matchingStrategy": "all",
            "q": "power",
            "limit": 5,
            "filter": ["status = active"],
            "attributesToHighlight": ["title"],
        }
        return response(
            200,
            {
                "data": {
                    "hits": [{"id": "a-1", "custom": {"score": 4}}],
                    "limit": 5,
                    "estimatedTotalHits": 1,
                    "processingTimeMs": 2,
                },
                "meta": {"request_id": "req-1", "region": "sh", "duration_ms": 3},
                "error": None,
            },
            request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient(
        "https://control.test",
        "token",
        search_url="https://search.test/",
        http_client=http_client,
    )

    result = client.search(
        "articles",
        query="power",
        limit=5,
        filter=["status = active"],
        attributes_to_highlight=["title"],
        raw_parameters={"matchingStrategy": "all"},
    )

    assert result.hits[0]["custom"] == {"score": 4}
    assert result.estimated_total_hits == 1
    assert result.meta.request_id == "req-1"
    assert result.meta.region == "sh"
    assert seen[0].headers["X-Request-ID"]
    assert seen[0].url.path != "/search"

    client.close()
    http_client.close()


def test_agent_discovery_filters_region_and_fails_over_once() -> None:
    attempted_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "control.test":
            assert request.url.path == "/api/v1/agents/online"
            assert dict(request.url.params) == {"region": "sh"}
            return response(
                200,
                {
                    "data": [
                        {
                            "id": "a",
                            "ip": "10.0.0.1",
                            "port": 8091,
                            "base_url": "https://a.test",
                            "region": "sh",
                            "weight": 100,
                        },
                        {
                            "id": "b",
                            "ip": "10.0.0.2",
                            "port": 8091,
                            "base_url": "https://b.test",
                            "region": "sh",
                            "weight": 50,
                        },
                        {
                            "id": "c",
                            "ip": "10.0.0.3",
                            "port": 8091,
                            "base_url": "https://c.test",
                            "region": "bj",
                            "weight": 1000,
                        },
                    ],
                    "message": "ok",
                },
                request,
            )

        attempted_hosts.append(request.url.host or "")
        if len(attempted_hosts) == 1:
            return response(
                503,
                {
                    "data": None,
                    "meta": {
                        "request_id": request.headers["X-Request-ID"],
                        "region": "sh",
                    },
                    "error": {
                        "code": "SEARCH_BACKEND_UNAVAILABLE",
                        "message": "busy",
                        "retryable": True,
                    },
                },
                request,
            )
        return response(
            200,
            {
                "data": {"hits": [{"id": "ok"}]},
                "meta": {"request_id": request.headers["X-Request-ID"], "region": "sh"},
                "error": None,
            },
            request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient(
        "https://control.test",
        "token",
        region="sh",
        max_retries=2,
        http_client=http_client,
    )
    client._sleep = lambda _: None

    assert client.search("articles", query="hello").hits == [{"id": "ok"}]
    assert len(attempted_hosts) == 2
    assert len(set(attempted_hosts)) == 2
    assert "c.test" not in attempted_hosts

    client.close()
    http_client.close()


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (401, {"data": None, "message": "bad token"}, AuthenticationError),
        (403, {"data": None, "message": "missing scope"}, PermissionDeniedError),
        (
            422,
            {"detail": [{"loc": ["body", "id"], "msg": "required"}]},
            ValidationError,
        ),
    ],
)
def test_control_errors_map_to_sdk_exceptions(
    status: int,
    payload: dict[str, Any],
    expected: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(status, payload, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient(
        "https://control.test", "token", max_retries=0, http_client=http_client
    )
    with pytest.raises(expected) as exc_info:
        client.health()
    assert getattr(exc_info.value, "status_code") == status
    client.close()
    http_client.close()


def test_validation_and_empty_strict_region_fail_before_search() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(200, {"data": [], "message": "ok"}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient(
        "https://control.test", "token", region="sh", http_client=http_client
    )

    with pytest.raises(ValidationError):
        client.upsert_document("bad collection", {"id": "a"})
    with pytest.raises(ValidationError):
        client.upsert_document("articles", {"id": ""})
    with pytest.raises(ValidationError):
        client.search("articles", limit=1001)
    with pytest.raises(NoSearchAgentError):
        client.search("articles", query="none")
    assert calls == 1

    client.close()
    http_client.close()


def test_control_retry_honors_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"data": None, "message": "slow down"},
                headers={"Retry-After": "1.5"},
                request=request,
            )
        return response(200, {"data": {"status": "healthy"}, "message": "ok"}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient("https://control.test", "token", http_client=http_client)
    client._sleep = delays.append

    assert client.health()["status"] == "healthy"
    assert calls == 2
    assert delays == [1.5]

    client.close()
    http_client.close()


def test_agent_cache_is_reused_across_searches() -> None:
    discovery_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal discovery_calls
        if request.url.host == "control.test":
            discovery_calls += 1
            return response(
                200,
                {
                    "data": [
                        {
                            "id": "a",
                            "ip": "10.0.0.1",
                            "port": 8091,
                            "base_url": "https://a.test",
                            "region": "sh",
                        }
                    ],
                    "message": "ok",
                },
                request,
            )
        return response(
            200,
            {
                "data": {"hits": []},
                "meta": {"request_id": request.headers["X-Request-ID"]},
                "error": None,
            },
            request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient("https://control.test", "token", http_client=http_client)

    client.search("articles")
    client.search("articles")
    assert discovery_calls == 1

    client.close()
    http_client.close()


def test_invalid_success_envelope_raises_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response(200, {"status": "healthy"}, request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient("https://control.test", "token", http_client=http_client)

    with pytest.raises(ProtocolError):
        client.health()

    client.close()
    http_client.close()


def test_sync_and_async_clients_expose_the_same_business_methods() -> None:
    methods = {
        "health",
        "upsert_document",
        "upsert_documents",
        "get_document",
        "list_documents",
        "delete_document",
        "list_indexes",
        "delete_index",
        "update_index_settings",
        "list_agents",
        "search",
    }
    assert methods <= set(dir(UniDataClient))
    assert methods <= set(dir(AsyncUniDataClient))


def test_non_retryable_api_error_preserves_search_diagnostics() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "data": None,
                "meta": {"request_id": "req-bad", "region": "sh"},
                "error": {
                    "code": "INVALID_SEARCH_REQUEST",
                    "message": "bad filter",
                    "retryable": False,
                },
            },
            headers={"Retry-After": "9"},
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = UniDataClient(
        "https://control.test",
        "token",
        search_url="https://search.test",
        http_client=http_client,
    )

    with pytest.raises(ApiError) as exc_info:
        client.search("articles")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_SEARCH_REQUEST"
    assert exc_info.value.request_id == "req-bad"
    assert exc_info.value.retry_after == "9"
    assert exc_info.value.retryable is False

    client.close()
    http_client.close()

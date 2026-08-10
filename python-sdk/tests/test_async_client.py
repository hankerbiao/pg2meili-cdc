from __future__ import annotations

import json

import httpx
import pytest

from melidata_sdk import AsyncMeliDataClient, ServiceUnavailableError, ValidationError


@pytest.mark.asyncio
async def test_async_client_matches_document_and_search_contracts() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/data/articles":
            return httpx.Response(
                201,
                json={
                    "data": {
                        "status": "success",
                        "id": "a-1",
                        "collection": "articles",
                    },
                    "message": "ok",
                },
                request=request,
            )
        if request.url.path == "/api/v1/collections/articles/search":
            assert json.loads(request.content)["q"] == "async"
            return httpx.Response(
                200,
                json={
                    "data": {"hits": [{"id": "a-1"}]},
                    "meta": {
                        "request_id": request.headers["X-Request-ID"],
                        "region": "sh",
                    },
                    "error": None,
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncMeliDataClient(
        "https://control.test",
        "token",
        search_url="https://search.test",
        http_client=http_client,
    )

    assert (await client.upsert_document("articles", {"id": "a-1"})).id == "a-1"
    assert (await client.search("articles", query="async")).hits == [{"id": "a-1"}]
    assert all(
        request.headers["Authorization"] == "Bearer token" for request in requests
    )

    await client.aclose()
    assert not http_client.is_closed
    await http_client.aclose()


@pytest.mark.asyncio
async def test_async_generic_request_uses_control_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/data/articles"
        assert json.loads(request.content) == {"id": "async-1"}
        assert request.headers["X-Trace"] == "sdk-test"
        assert request.headers["Authorization"] == "Bearer api-key"
        return httpx.Response(
            201,
            json={"data": {"id": "async-1"}, "message": "ok"},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncMeliDataClient(
        "https://control.test", "api-key", http_client=http_client
    )

    assert await client.request(
        "POST",
        "/api/v1/data/articles",
        json={"id": "async-1"},
        headers={"X-Trace": "sdk-test"},
    ) == {"id": "async-1"}
    with pytest.raises(ValidationError):
        await client.request("GET", "//other.test/path")
    with pytest.raises(ValidationError, match="managed by the MeliData SDK"):
        await client.request("GET", "/health", headers={"User-Agent": "other"})

    await client.aclose()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_async_search_does_not_retry_non_retryable_error() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            503,
            json={
                "data": None,
                "meta": {"request_id": "req-1"},
                "error": {
                    "code": "CONFIGURATION_ERROR",
                    "message": "broken",
                    "retryable": False,
                },
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncMeliDataClient(
        "https://control.test",
        "token",
        search_url="https://search.test",
        max_retries=2,
        http_client=http_client,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await client.search("articles")
    assert exc_info.value.retryable is False
    assert calls == 1

    await client.aclose()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_async_agent_discovery_fails_over_to_a_distinct_agent() -> None:
    search_hosts: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "control.test":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "a",
                            "ip": "10.0.0.1",
                            "port": 8091,
                            "base_url": "https://a.test",
                            "region": "sh",
                        },
                        {
                            "id": "b",
                            "ip": "10.0.0.2",
                            "port": 8091,
                            "base_url": "https://b.test",
                            "region": "sh",
                        },
                    ],
                    "message": "ok",
                },
                request=request,
            )
        search_hosts.append(request.url.host or "")
        if len(search_hosts) == 1:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(
            200,
            json={
                "data": {"hits": [{"id": "ok"}]},
                "meta": {"request_id": request.headers["X-Request-ID"], "region": "sh"},
                "error": None,
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncMeliDataClient(
        "https://control.test",
        "token",
        region="sh",
        http_client=http_client,
    )

    async def no_sleep(_: float) -> None:
        return None

    client._sleep = no_sleep
    assert (await client.search("articles")).hits == [{"id": "ok"}]
    assert len(search_hosts) == 2
    assert len(set(search_hosts)) == 2

    await client.aclose()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_owned_async_client_is_closed_by_context_manager() -> None:
    async with AsyncMeliDataClient(
        "https://control.test",
        "token",
        search_url="https://search.test",
    ) as client:
        owned_http_client = client._http
        assert not owned_http_client.is_closed
    assert owned_http_client.is_closed

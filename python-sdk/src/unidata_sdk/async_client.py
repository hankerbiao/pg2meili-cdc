from __future__ import annotations

import asyncio
import ssl
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from ._common import (
    ClientState,
    Timeout,
    build_search_payload,
    encode_document_id,
    parse_agents,
    parse_batch_upsert,
    parse_document,
    parse_document_write,
    parse_documents,
    parse_index_delete,
    parse_index_settings,
    parse_indexes,
    parse_search_result,
)
from ._protocol import parse_control_response, parse_search_response
from ._retry import is_retryable, retry_delay
from ._validation import (
    validate_collection,
    validate_document,
    validate_documents,
    validate_page,
    validate_request_path,
    validate_string_list,
)
from .exceptions import (
    NoSearchAgentError,
    TransportError,
    UniDataError,
    ValidationError,
)
from .models import (
    Agent,
    BatchUpsertResult,
    DocumentWriteResult,
    IndexDeleteResult,
    IndexSettingsResult,
    SearchResult,
)


class AsyncUniDataClient:
    """Asynchronous client for MeliData and its distributed search Agents."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        search_url: str | None = None,
        region: str | None = None,
        timeout: Timeout = 10.0,
        max_retries: int = 2,
        agent_cache_ttl: float = 30.0,
        verify: bool | str | ssl.SSLContext = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._state = ClientState(
            base_url,
            api_key,
            search_url=search_url,
            region=region,
            max_retries=max_retries,
            agent_cache_ttl=agent_cache_ttl,
        )
        self._http = http_client or httpx.AsyncClient(timeout=timeout, verify=verify)
        self._owns_http_client = http_client is None
        self._timeout = timeout
        self._sleep = asyncio.sleep

    async def __aenter__(self) -> AsyncUniDataClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Call a MeliData control-plane API and return its response data."""
        if not isinstance(method, str) or not method.strip():
            raise ValidationError("method must be a non-empty string")
        return await self._control_request(
            method.strip().upper(),
            validate_request_path(path),
            params=params,
            json=json,
            headers=headers,
        )

    async def health(self) -> dict[str, Any]:
        data = await self._control_request("GET", "/health")
        return parse_document(data)

    async def upsert_document(
        self,
        collection: str,
        document: Mapping[str, Any],
    ) -> DocumentWriteResult:
        collection = validate_collection(collection)
        data = await self._control_request(
            "POST",
            f"/api/v1/data/{collection}",
            json=validate_document(document),
        )
        return parse_document_write(data)

    async def upsert_documents(
        self,
        collection: str,
        documents: Sequence[Mapping[str, Any]],
    ) -> BatchUpsertResult:
        collection = validate_collection(collection)
        data = await self._control_request(
            "POST",
            f"/api/v1/data/{collection}/batch",
            json={"items": validate_documents(documents)},
        )
        return parse_batch_upsert(data)

    async def get_document(
        self, collection: str, document_id: str | int
    ) -> dict[str, Any]:
        collection = validate_collection(collection)
        data = await self._control_request(
            "GET",
            f"/api/v1/data/{collection}/{encode_document_id(document_id)}",
        )
        return parse_document(data)

    async def list_documents(
        self,
        collection: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        collection = validate_collection(collection)
        validate_page(limit=limit, offset=offset, max_limit=100)
        data = await self._control_request(
            "GET",
            f"/api/v1/data/{collection}",
            params={"limit": limit, "offset": offset},
        )
        return parse_documents(data)

    async def delete_document(
        self,
        collection: str,
        document_id: str | int,
    ) -> DocumentWriteResult:
        collection = validate_collection(collection)
        data = await self._control_request(
            "DELETE",
            f"/api/v1/data/{collection}/{encode_document_id(document_id)}",
        )
        return parse_document_write(data)

    async def list_indexes(self, *, limit: int = 100, offset: int = 0) -> list[str]:
        validate_page(limit=limit, offset=offset, max_limit=500)
        data = await self._control_request(
            "GET",
            "/api/v1/indexes",
            params={"limit": limit, "offset": offset},
        )
        return parse_indexes(data)

    async def delete_index(self, collection: str) -> IndexDeleteResult:
        collection = validate_collection(collection)
        data = await self._control_request("DELETE", f"/api/v1/indexes/{collection}")
        return parse_index_delete(data)

    async def update_index_settings(
        self,
        collection: str,
        *,
        filterable_attributes: Sequence[str],
        sortable_attributes: Sequence[str],
    ) -> IndexSettingsResult:
        collection = validate_collection(collection)
        data = await self._control_request(
            "POST",
            f"/api/v1/indexes/{collection}/settings",
            json={
                "filterableAttributes": validate_string_list(
                    filterable_attributes,
                    field_name="filterable_attributes",
                ),
                "sortableAttributes": validate_string_list(
                    sortable_attributes,
                    field_name="sortable_attributes",
                ),
            },
        )
        return parse_index_settings(data)

    async def list_agents(self) -> list[Agent]:
        params = {"region": self._state.region} if self._state.region else None
        data = await self._control_request(
            "GET", "/api/v1/agents/online", params=params
        )
        return self._state.agent_pool.update(parse_agents(data))

    async def search(
        self,
        collection: str,
        *,
        query: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        filter: str | Sequence[str] | None = None,
        attributes_to_highlight: Sequence[str] | None = None,
        attributes_to_retrieve: Sequence[str] | None = None,
        attributes_to_crop: Sequence[str] | None = None,
        crop_length: int | None = None,
        show_ranking_score: bool | None = None,
        raw_parameters: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> SearchResult:
        collection = validate_collection(collection)
        payload = build_search_payload(
            query=query,
            offset=offset,
            limit=limit,
            filter=filter,
            attributes_to_highlight=attributes_to_highlight,
            attributes_to_retrieve=attributes_to_retrieve,
            attributes_to_crop=attributes_to_crop,
            crop_length=crop_length,
            show_ranking_score=show_ranking_score,
            raw_parameters=raw_parameters,
        )
        logical_request_id = request_id or uuid.uuid4().hex
        if self._state.search_url:
            return await self._search_fixed(
                self._state.search_url,
                collection,
                payload,
                logical_request_id,
            )
        return await self._search_discovered(collection, payload, logical_request_id)

    async def _control_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        for attempt in range(self._state.max_retries + 1):
            try:
                response = await self._http.request(
                    method,
                    self._state.control_url(path),
                    headers=self._state.request_headers(headers),
                    params=params,
                    json=json,
                    timeout=self._timeout,
                )
                return parse_control_response(response)
            except httpx.TransportError as error:
                sdk_error: UniDataError = TransportError("Unable to connect to MeliData")
                sdk_error.__cause__ = error
            except UniDataError as error:
                sdk_error = error
            if attempt >= self._state.max_retries or not is_retryable(sdk_error):
                raise sdk_error
            await self._sleep(retry_delay(sdk_error, attempt))
        raise AssertionError("unreachable")

    async def _search_fixed(
        self,
        base_url: str,
        collection: str,
        payload: dict[str, Any],
        request_id: str,
    ) -> SearchResult:
        for attempt in range(self._state.max_retries + 1):
            try:
                return await self._search_once(
                    base_url, collection, payload, request_id
                )
            except UniDataError as error:
                if attempt >= self._state.max_retries or not is_retryable(error):
                    raise
                await self._sleep(retry_delay(error, attempt))
        raise AssertionError("unreachable")

    async def _search_discovered(
        self,
        collection: str,
        payload: dict[str, Any],
        request_id: str,
    ) -> SearchResult:
        candidates = await self._search_candidates()
        if not candidates:
            raise NoSearchAgentError(self._no_agent_message())

        attempts = 0
        refreshed = False
        attempted_urls: set[str] = set()
        last_error: UniDataError | None = None
        while attempts <= self._state.max_retries:
            while candidates:
                agent = candidates.pop(0)
                if agent.base_url in attempted_urls:
                    continue
                attempted_urls.add(agent.base_url)
                try:
                    return await self._search_once(
                        agent.base_url, collection, payload, request_id
                    )
                except UniDataError as error:
                    attempts += 1
                    last_error = error
                    if not is_retryable(error) or attempts > self._state.max_retries:
                        raise
                    await self._sleep(retry_delay(error, attempts - 1))
                    break

            if candidates:
                continue
            if not refreshed and last_error is not None:
                refreshed = True
                self._state.agent_pool.invalidate()
                candidates = [
                    agent
                    for agent in await self._search_candidates()
                    if agent.base_url not in attempted_urls
                ]
                if candidates:
                    continue
            if last_error is not None:
                raise last_error
            raise NoSearchAgentError(self._no_agent_message())
        if last_error is not None:
            raise last_error
        raise NoSearchAgentError(self._no_agent_message())

    async def _search_candidates(self) -> list[Agent]:
        if not self._state.agent_pool.is_fresh:
            await self.list_agents()
        return self._state.agent_pool.candidates()

    async def _search_once(
        self,
        base_url: str,
        collection: str,
        payload: dict[str, Any],
        request_id: str,
    ) -> SearchResult:
        headers = {**self._state.headers, "X-Request-ID": request_id}
        try:
            response = await self._http.post(
                self._state.search_endpoint(base_url, collection),
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TransportError as error:
            raise TransportError(
                "Unable to connect to a search Agent", request_id=request_id
            ) from error
        data, meta = parse_search_response(response)
        return parse_search_result(data, meta)

    def _no_agent_message(self) -> str:
        if self._state.region:
            return (
                f"No online search Agent is available in region {self._state.region!r}"
            )
        return "No online search Agent is available"

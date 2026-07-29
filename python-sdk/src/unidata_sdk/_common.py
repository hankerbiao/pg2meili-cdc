from __future__ import annotations

import ssl
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from ._discovery import AgentPool
from ._validation import (
    normalize_base_url,
    validate_collection,
    validate_search_limit,
    validate_string_list,
)
from ._version import __version__
from .exceptions import ProtocolError, ValidationError
from .models import (
    Agent,
    BatchUpsertResult,
    DocumentWriteResult,
    IndexDeleteResult,
    IndexSettingsResult,
    SearchMeta,
    SearchResult,
)


Timeout = float | httpx.Timeout
Verify = bool | str | ssl.SSLContext


class ClientState:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        search_url: str | None,
        region: str | None,
        max_retries: int,
        agent_cache_ttl: float,
    ) -> None:
        self.base_url = normalize_base_url(base_url, field_name="base_url")
        self.search_url = (
            normalize_base_url(search_url, field_name="search_url")
            if search_url is not None
            else None
        )
        if not isinstance(token, str) or not token.strip():
            raise ValidationError("token must be a non-empty string")
        if region is not None and (not isinstance(region, str) or not region.strip()):
            raise ValidationError("region must be a non-empty string when provided")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries < 0
        ):
            raise ValidationError("max_retries must be a non-negative integer")
        if not isinstance(agent_cache_ttl, (int, float)) or agent_cache_ttl < 0:
            raise ValidationError("agent_cache_ttl must be non-negative")

        self.token = token.strip()
        self.region = region.strip() if region is not None else None
        self.max_retries = max_retries
        self.agent_pool = AgentPool(
            region=self.region, cache_ttl=float(agent_cache_ttl)
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": f"unidata-sdk/{__version__}",
        }

    def control_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def search_endpoint(self, base_url: str, collection: str) -> str:
        collection = validate_collection(collection)
        return f"{base_url}/api/v1/collections/{collection}/search"


def encode_document_id(document_id: str | int) -> str:
    if isinstance(document_id, bool) or not isinstance(document_id, (str, int)):
        raise ValidationError("document id must be a string or integer")
    value = str(document_id)
    if not value:
        raise ValidationError("document id must not be empty")
    return quote(value, safe="")


def build_search_payload(
    *,
    query: str | None,
    offset: int | None,
    limit: int | None,
    filter: str | Sequence[str] | None,
    attributes_to_highlight: Sequence[str] | None,
    attributes_to_retrieve: Sequence[str] | None,
    attributes_to_crop: Sequence[str] | None,
    crop_length: int | None,
    show_ranking_score: bool | None,
    raw_parameters: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if raw_parameters is not None and not isinstance(raw_parameters, Mapping):
        raise ValidationError("raw_parameters must be a mapping")
    validate_search_limit(limit, raw_parameters)
    payload = dict(raw_parameters or {})

    if query is not None:
        if not isinstance(query, str):
            raise ValidationError("query must be a string")
        payload["q"] = query
    if offset is not None:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValidationError("search offset must be a non-negative integer")
        payload["offset"] = offset
    if limit is not None:
        payload["limit"] = limit
    if filter is not None:
        if isinstance(filter, str):
            payload["filter"] = filter
        else:
            payload["filter"] = validate_string_list(filter, field_name="filter")
    if attributes_to_highlight is not None:
        payload["attributesToHighlight"] = validate_string_list(
            attributes_to_highlight,
            field_name="attributes_to_highlight",
        )
    if attributes_to_retrieve is not None:
        payload["attributesToRetrieve"] = validate_string_list(
            attributes_to_retrieve,
            field_name="attributes_to_retrieve",
        )
    if attributes_to_crop is not None:
        payload["attributesToCrop"] = validate_string_list(
            attributes_to_crop,
            field_name="attributes_to_crop",
        )
    if crop_length is not None:
        if (
            isinstance(crop_length, bool)
            or not isinstance(crop_length, int)
            or crop_length < 0
        ):
            raise ValidationError("crop_length must be a non-negative integer")
        payload["cropLength"] = crop_length
    if show_ranking_score is not None:
        if not isinstance(show_ranking_score, bool):
            raise ValidationError("show_ranking_score must be a boolean")
        payload["showRankingScore"] = show_ranking_score
    return payload


def parse_document_write(data: Any) -> DocumentWriteResult:
    item = _mapping(data, "document write")
    return DocumentWriteResult(
        status=_string(item, "status"),
        id=_string(item, "id"),
        collection=_string(item, "collection"),
    )


def parse_batch_upsert(data: Any) -> BatchUpsertResult:
    item = _mapping(data, "batch upsert")
    ids = item.get("ids")
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
        raise ProtocolError("UniData returned invalid batch upsert ids")
    return BatchUpsertResult(
        status=_string(item, "status"),
        collection=_string(item, "collection"),
        count=_int(item, "count"),
        ids=list(ids),
    )


def parse_index_delete(data: Any) -> IndexDeleteResult:
    item = _mapping(data, "index delete")
    return IndexDeleteResult(
        status=_string(item, "status"),
        collection=_string(item, "collection"),
        deleted_count=_int(item, "deleted_count"),
    )


def parse_index_settings(data: Any) -> IndexSettingsResult:
    item = _mapping(data, "index settings")
    return IndexSettingsResult(
        status=_string(item, "status"),
        collection=_string(item, "collection"),
        index_uid=_string(item, "index_uid"),
    )


def parse_agents(data: Any) -> list[Agent]:
    if not isinstance(data, list):
        raise ProtocolError("UniData returned an invalid Agent list")
    agents: list[Agent] = []
    for raw in data:
        item = _mapping(raw, "Agent")
        ip = _string(item, "ip")
        port = _int(item, "port")
        raw_base_url = item.get("base_url") or f"http://{ip}:{port}"
        try:
            base_url = normalize_base_url(
                str(raw_base_url), field_name="Agent base_url"
            )
        except ValidationError as error:
            raise ProtocolError(
                "UniData returned an Agent with an invalid base_url"
            ) from error
        weight = item.get("weight", 100)
        if isinstance(weight, bool) or not isinstance(weight, int):
            weight = 100
        agents.append(
            Agent(
                id=_string(item, "id"),
                ip=ip,
                port=port,
                base_url=base_url,
                hostname=_optional_string(item.get("hostname")),
                region=_optional_string(item.get("region")),
                status=_optional_string(item.get("status")) or "ready",
                weight=max(1, min(1000, weight)),
                version=_optional_string(item.get("version")),
                last_seen_at=_optional_string(item.get("last_seen_at")),
            )
        )
    return agents


def parse_documents(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list) or any(
        not isinstance(item, Mapping) for item in data
    ):
        raise ProtocolError("UniData returned an invalid document list")
    return [dict(item) for item in data]


def parse_document(data: Any) -> dict[str, Any]:
    return dict(_mapping(data, "document"))


def parse_indexes(data: Any) -> list[str]:
    if not isinstance(data, list) or any(not isinstance(item, str) for item in data):
        raise ProtocolError("UniData returned an invalid index list")
    return list(data)


def parse_search_result(data: Any, meta: SearchMeta) -> SearchResult:
    item = _mapping(data, "search")
    hits = item.get("hits")
    if not isinstance(hits, list) or any(not isinstance(hit, Mapping) for hit in hits):
        raise ProtocolError("Search Agent returned invalid hits")
    return SearchResult(
        hits=[dict(hit) for hit in hits],
        meta=meta,
        offset=_optional_int(item.get("offset")),
        limit=_optional_int(item.get("limit")),
        estimated_total_hits=_optional_int(item.get("estimatedTotalHits")),
        processing_time_ms=_optional_int(item.get("processingTimeMs")),
        raw=dict(item),
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError(f"Service returned invalid {name} data")
    return value


def _string(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise ProtocolError(f"Service response field {key!r} must be a string")
    return value


def _int(item: Mapping[str, Any], key: str) -> int:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"Service response field {key!r} must be an integer")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DocumentWriteResult:
    status: str
    id: str
    collection: str


@dataclass(frozen=True, slots=True)
class BatchUpsertResult:
    status: str
    collection: str
    count: int
    ids: list[str]


@dataclass(frozen=True, slots=True)
class IndexDeleteResult:
    status: str
    collection: str
    deleted_count: int


@dataclass(frozen=True, slots=True)
class IndexSettingsResult:
    status: str
    collection: str
    index_uid: str


@dataclass(frozen=True, slots=True)
class Agent:
    id: str
    ip: str
    port: int
    base_url: str
    hostname: str | None = None
    region: str | None = None
    status: str = "ready"
    weight: int = 100
    version: str | None = None
    last_seen_at: str | None = None


@dataclass(frozen=True, slots=True)
class SearchMeta:
    request_id: str
    region: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: list[dict[str, Any]]
    meta: SearchMeta
    offset: int | None = None
    limit: int | None = None
    estimated_total_hits: int | None = None
    processing_time_ms: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .exceptions import ValidationError


_COLLECTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def normalize_base_url(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty URL")
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValidationError(f"{field_name} must use http or https")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValidationError(
            f"{field_name} must not contain credentials, a query, or a fragment"
        )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def validate_request_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise ValidationError("path must be a relative API path starting with one '/'")
    parts = urlsplit(path)
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise ValidationError("path must not contain a URL, query, or fragment")
    return path


def validate_collection(collection: str) -> str:
    if not isinstance(collection, str) or not _COLLECTION_PATTERN.fullmatch(collection):
        raise ValidationError(
            "collection must be 1-128 ASCII letters, numbers, underscores, or hyphens"
        )
    return collection


def validate_document(document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise ValidationError("document must be a mapping")
    document_id = document.get("id")
    if not isinstance(document_id, str) or not document_id:
        raise ValidationError("document id must be a non-empty string")
    return dict(document)


def validate_documents(documents: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if (
        isinstance(documents, (str, bytes))
        or not isinstance(documents, Sequence)
        or not documents
    ):
        raise ValidationError("documents must be a non-empty sequence")
    return [validate_document(document) for document in documents]


def validate_page(*, limit: int, offset: int, max_limit: int) -> None:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= max_limit
    ):
        raise ValidationError(f"limit must be an integer between 1 and {max_limit}")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValidationError("offset must be a non-negative integer")


def validate_search_limit(
    limit: int | None, raw_parameters: Mapping[str, Any] | None
) -> None:
    raw_limit = raw_parameters.get("limit") if raw_parameters else None
    value = limit if limit is not None else raw_limit
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
        raise ValidationError("search limit must be an integer between 1 and 1000")


def validate_string_list(value: Sequence[str], *, field_name: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValidationError(f"{field_name} must be a sequence of strings")
    result = list(value)
    if any(not isinstance(item, str) for item in result):
        raise ValidationError(f"{field_name} must contain only strings")
    return result

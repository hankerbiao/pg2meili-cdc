from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, NoReturn

import httpx

from .exceptions import (
    ApiError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    ProtocolError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)
from .models import SearchMeta


_NON_RETRYABLE_STATUSES = {400, 401, 403, 404, 405, 413, 422}
_RETRYABLE_STATUSES = {429, 502, 503, 504}


def parse_control_response(response: httpx.Response) -> Any:
    payload = _json_payload(response)
    if not response.is_success:
        message = _control_error_message(response, payload)
        _raise_api_error(
            response,
            message=message,
            code=None,
            response_body=payload,
        )

    if not isinstance(payload, Mapping) or "data" not in payload:
        raise ProtocolError("UniData returned an invalid success response")
    return payload["data"]


def parse_search_response(response: httpx.Response) -> tuple[Any, SearchMeta]:
    payload = _json_payload(response)
    payload_mapping = payload if isinstance(payload, Mapping) else {}
    meta_payload = payload_mapping.get("meta")
    if not isinstance(meta_payload, Mapping):
        meta_payload = {}
    request_id = str(
        meta_payload.get("request_id") or response.headers.get("X-Request-ID") or ""
    )
    error_payload = payload_mapping.get("error")

    if not response.is_success or error_payload is not None:
        error_mapping = error_payload if isinstance(error_payload, Mapping) else {}
        message = str(
            error_mapping.get("message") or _control_error_message(response, payload)
        )
        code = error_mapping.get("code")
        retryable = error_mapping.get("retryable")
        _raise_api_error(
            response,
            message=message,
            code=str(code) if code is not None else None,
            retryable=retryable if isinstance(retryable, bool) else None,
            request_id=request_id or None,
            response_body=payload,
        )

    if (
        not isinstance(payload, Mapping)
        or "data" not in payload
        or "error" not in payload
    ):
        raise ProtocolError("Search Agent returned an invalid success response")
    meta = SearchMeta(
        request_id=request_id,
        region=_optional_string(meta_payload.get("region")),
        duration_ms=_optional_int(meta_payload.get("duration_ms")),
    )
    return payload["data"], meta


def _json_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _control_error_message(response: httpx.Response, payload: Any) -> str:
    if isinstance(payload, Mapping):
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        if isinstance(detail, list):
            messages = []
            for item in detail:
                if not isinstance(item, Mapping):
                    continue
                location = ".".join(str(part) for part in item.get("loc", []))
                text = str(item.get("msg") or "invalid value")
                messages.append(f"{location}: {text}" if location else text)
            if messages:
                return "; ".join(messages)
    text = response.text.strip()
    return text[:1000] if text else f"HTTP {response.status_code}"


def _raise_api_error(
    response: httpx.Response,
    *,
    message: str,
    code: str | None,
    retryable: bool | None = None,
    request_id: str | None = None,
    response_body: Any = None,
) -> NoReturn:
    status = response.status_code
    if status in _NON_RETRYABLE_STATUSES:
        is_retryable = False
    elif retryable is not None:
        is_retryable = retryable
    else:
        is_retryable = status in _RETRYABLE_STATUSES

    error_type: type[ApiError]
    if status == 401:
        error_type = AuthenticationError
    elif status == 403:
        error_type = PermissionDeniedError
    elif status == 404:
        error_type = NotFoundError
    elif status == 429:
        error_type = RateLimitError
    elif status == 422:
        raise ValidationError(
            message,
            status_code=status,
            code=code,
            request_id=request_id or response.headers.get("X-Request-ID"),
            retry_after=response.headers.get("Retry-After"),
            response_body=response_body,
        )
    elif status in {502, 503, 504}:
        error_type = ServiceUnavailableError
    else:
        error_type = ApiError

    kwargs = {
        "status_code": status,
        "code": code,
        "retryable": is_retryable,
        "request_id": request_id or response.headers.get("X-Request-ID"),
        "retry_after": response.headers.get("Retry-After"),
        "response_body": response_body,
    }
    raise error_type(message, **kwargs)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

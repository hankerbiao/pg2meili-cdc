from __future__ import annotations

import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .exceptions import ApiError, TransportError, UniDataError


def is_retryable(error: UniDataError) -> bool:
    return isinstance(error, TransportError) or (
        isinstance(error, ApiError) and error.retryable
    )


def retry_delay(error: UniDataError, retry_index: int) -> float:
    retry_after = getattr(error, "retry_after", None)
    parsed = _parse_retry_after(retry_after)
    if parsed is not None:
        return min(parsed, 60.0)
    base = min(0.2 * (2**retry_index), 5.0)
    return base + random.random() * base * 0.25


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())

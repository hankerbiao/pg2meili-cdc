from __future__ import annotations

from typing import Any


class UniDataError(Exception):
    """Base class for all SDK errors."""


class ValidationError(UniDataError):
    """Raised for local input errors and HTTP validation responses."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
        retry_after: str | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = False
        self.request_id = request_id
        self.retry_after = retry_after
        self.response_body = response_body


class ProtocolError(UniDataError):
    """Raised when a service returns an invalid success response."""


class TransportError(UniDataError):
    """Raised when an HTTP request cannot reach a service."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.retryable = True
        self.status_code: int | None = None
        self.code = "TRANSPORT_ERROR"
        self.retry_after: str | None = None


class ApiError(UniDataError):
    """An error response returned by UniData or a search Agent."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        retryable: bool = False,
        request_id: str | None = None,
        retry_after: str | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
        self.request_id = request_id
        self.retry_after = retry_after
        self.response_body = response_body


class AuthenticationError(ApiError):
    """The supplied token is missing, invalid, or expired."""


class PermissionDeniedError(ApiError):
    """The token does not have the required scope."""


class NotFoundError(ApiError):
    """The requested document, index, or search collection was not found."""


class RateLimitError(ApiError):
    """The service rejected the request because of rate limiting."""


class ServiceUnavailableError(ApiError):
    """A backend service is temporarily unavailable."""


class NoSearchAgentError(UniDataError):
    """No online search Agent matches the configured region."""

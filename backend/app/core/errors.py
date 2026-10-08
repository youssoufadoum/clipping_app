"""Normalized application errors.

Every error that reaches a client has a stable machine-readable ``code`` and a
safe human-readable ``message``. Internal details (stack traces, provider
payloads, file paths) are logged server side only.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"
    message = "The request could not be processed."
    retryable = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        if retryable is not None:
            self.retryable = retryable
        super().__init__(self.message)


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Authentication is required."


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "You do not have access to this resource."


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "The requested resource was not found."


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "The resource is not in a state that allows this action."


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"
    message = "The request contains invalid data."


class QuotaExceeded(AppError):
    status_code = 402
    code = "QUOTA_EXCEEDED"
    message = "This action exceeds your plan's limits."


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests. Please wait a moment and try again."
    retryable = True


class ServiceUnavailable(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    message = "This feature is not configured on this server."


class ProcessingError(Exception):
    """Raised inside workers. ``code``/``safe_message`` are persisted on the job."""

    def __init__(self, code: str, safe_message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        super().__init__(f"{code}: {safe_message}")

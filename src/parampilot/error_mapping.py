"""Canonical error-envelope parsing and typed exception selection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError

from parampilot.errors import (
    AuthenticationError,
    ConflictError,
    IdempotencyError,
    InvalidRequestError,
    JobError,
    LockedError,
    NotFoundError,
    ParamPilotHTTPError,
    PayloadTooLargeError,
    PermissionDeniedError,
    PreconditionRequiredError,
    RateLimitError,
    RequestValidationError,
    RevisionConflictError,
    ServerError,
    TrainingRequiredError,
    UnsupportedMediaTypeError,
)
from parampilot.models import PublicApiErrorResponse

IDEMPOTENCY_CODES = frozenset({"idempotency_in_progress", "idempotency_key_reused"})
JOB_CODES = frozenset(
    {"job_not_complete", "job_failed", "job_canceled", "job_not_cancelable"}
)


def _retry_after(response: httpx.Response) -> float | None:
    """Parse a nonnegative delta-seconds Retry-After header.

    Args:
        response: Unsuccessful HTTPX response.

    Returns:
        Parsed delay or ``None`` for absent/unsupported values.

    """
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _redact(value: Any, secret: str) -> Any:
    """Recursively remove the configured token from decoded server data.

    Args:
        value: Decoded JSON-compatible value.
        secret: Exact credential that must never enter an exception.

    Returns:
        Independent redacted value.

    """
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item, secret) for key, item in value.items()}
    return value


def _error_type(status_code: int, code: str) -> type[ParamPilotHTTPError]:
    """Select the public exception class for one canonical failure.

    Args:
        status_code: HTTP response status.
        code: Stable server error code.

    Returns:
        Most specific public exception type.

    """
    if code == "training_required":
        return TrainingRequiredError
    if code in IDEMPOTENCY_CODES:
        return IdempotencyError
    if code in JOB_CODES:
        return JobError
    by_status: dict[int, type[ParamPilotHTTPError]] = {
        400: InvalidRequestError,
        401: AuthenticationError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        412: RevisionConflictError,
        413: PayloadTooLargeError,
        415: UnsupportedMediaTypeError,
        422: RequestValidationError,
        423: LockedError,
        428: PreconditionRequiredError,
        429: RateLimitError,
        500: ServerError,
        503: ServerError,
        504: ServerError,
    }
    return by_status.get(status_code, ParamPilotHTTPError)


def response_error(
    response: httpx.Response,
    *,
    operation_id: str | None,
    secret: str,
) -> ParamPilotHTTPError:
    """Convert an unsuccessful response to a typed secret-safe exception.

    Args:
        response: Unsuccessful HTTPX response.
        operation_id: Stable operation identifier when known.
        secret: Configured bearer credential to redact.

    Returns:
        Typed SDK exception ready to raise.

    """
    try:
        decoded = response.json()
        redacted = _redact(decoded, secret)
        envelope = PublicApiErrorResponse.model_validate(redacted)
    except (ValueError, ValidationError):
        return ParamPilotHTTPError(
            response.status_code,
            response.headers.get("X-Request-ID"),
            operation_id=operation_id,
            retry_after=_retry_after(response),
        )
    detail = envelope.error
    issues = [issue.model_dump(mode="json", by_alias=True) for issue in detail.issues]
    context = detail.context
    error_type = _error_type(response.status_code, detail.code)
    return error_type(
        response.status_code,
        detail.request_id,
        code=detail.code,
        message=detail.message,
        retryable=detail.retryable,
        issues=issues,
        context=context if isinstance(context, Mapping) else None,
        operation_id=operation_id,
        retry_after=_retry_after(response),
    )

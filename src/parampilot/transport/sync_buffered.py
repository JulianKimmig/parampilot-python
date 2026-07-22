"""Buffered HTTPX request execution for the synchronous SDK transport."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from parampilot.configuration import ClientConfiguration
from parampilot.error_mapping import response_error
from parampilot.errors import ParamPilotHTTPError, TransportError
from parampilot.operations import Operation
from parampilot.serialization import query_items


def _delay(
    configuration: ClientConfiguration,
    attempt: int,
    error: ParamPilotHTTPError | None,
) -> None:
    """Wait one bounded buffered-request retry delay.

    Args:
        configuration: Validated client retry settings.
        attempt: Zero-based failed attempt number.
        error: Optional canonical server error with Retry-After metadata.

    """
    retry_after = error.retry_after if error is not None else None
    delay = (
        retry_after
        if retry_after is not None
        else configuration.retry_backoff * (2**attempt)
    )
    time.sleep(min(delay, 30.0))


def send_buffered_response(
    *,
    client: httpx.Client,
    configuration: ClientConfiguration,
    operation: Operation | None,
    method: str,
    path: str,
    params: Mapping[str, Any] | None,
    json_body: Any,
    headers: Mapping[str, str],
    files: Mapping[str, tuple[str, bytes, str]] | None,
    allow_not_modified: bool,
) -> httpx.Response:
    """Execute sync buffered attempts with one stable logical identity.

    Args:
        client: Reusable synchronous HTTPX client.
        configuration: Validated connection and retry settings.
        operation: Generated operation or ``None`` for advanced requests.
        method: Uppercase HTTP method.
        path: Rooted request path.
        params: Optional query mapping.
        json_body: Optional JSON-compatible body.
        headers: Complete stable authenticated headers.
        files: Optional byte-backed multipart fields.
        allow_not_modified: Whether HTTP 304 is successful.

    Returns:
        Successful buffered HTTPX response.

    Raises:
        TransportError: If HTTPX fails beyond the safe retry budget.
        ParamPilotHTTPError: If the server returns an unsuccessful response.

    """
    operation_id = operation.operation_id if operation is not None else None
    retryable = operation is not None and operation.automatically_retryable
    for attempt in range(configuration.max_retries + 1):
        try:
            response = client.request(
                method,
                configuration.endpoint(path),
                params=httpx.QueryParams(query_items(params)),
                json=json_body,
                files=files,
                headers=headers,
                timeout=configuration.timeout,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            if retryable and attempt < configuration.max_retries:
                _delay(configuration, attempt, None)
                continue
            raise TransportError(
                "The ParamPilot API request could not be completed",
                operation_id,
            ) from None
        if response.is_success or (allow_not_modified and response.status_code == 304):
            return response
        error = response_error(
            response,
            operation_id=operation_id,
            secret=configuration.token,
        )
        if retryable and error.retryable and attempt < configuration.max_retries:
            _delay(configuration, attempt, error)
            continue
        raise error
    raise RuntimeError("unreachable retry state")

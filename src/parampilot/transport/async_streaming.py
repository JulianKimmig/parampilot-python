"""Unbuffered HTTPX response opening for the asynchronous SDK transport."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from parampilot.configuration import ClientConfiguration
from parampilot.error_mapping import response_error
from parampilot.errors import TransportError
from parampilot.operations import Operation
from parampilot.serialization import query_items


async def _delay(
    configuration: ClientConfiguration,
    attempt: int,
    retry_after: float | None,
) -> None:
    """Wait one bounded streaming retry delay.

    Args:
        configuration: Validated client retry settings.
        attempt: Zero-based failed attempt number.
        retry_after: Optional server-declared delay.

    """
    delay = (
        retry_after
        if retry_after is not None
        else configuration.retry_backoff * (2**attempt)
    )
    await asyncio.sleep(min(delay, 30.0))


async def open_stream_response(
    *,
    client: httpx.AsyncClient,
    configuration: ClientConfiguration,
    operation: Operation,
    path: str,
    params: Mapping[str, Any] | None,
    json_body: Any,
    headers: Mapping[str, str],
    allow_not_modified: bool,
) -> httpx.Response:
    """Open a successful unbuffered response with conservative retries.

    Args:
        client: Reusable asynchronous HTTPX client.
        configuration: Validated connection and retry settings.
        operation: Generated method/retry metadata.
        path: Fully rendered rooted path.
        params: Optional typed query mapping.
        json_body: Optional JSON-compatible request body.
        headers: Complete stable authenticated headers.
        allow_not_modified: Whether HTTP 304 is a non-error response.

    Returns:
        Open successful response owned by the caller.

    Raises:
        TransportError: If HTTPX cannot open the stream within the retry budget.
        ParamPilotHTTPError: If the server returns a terminal error response.

    """
    for attempt in range(configuration.max_retries + 1):
        request = client.build_request(
            operation.method,
            configuration.endpoint(path),
            params=httpx.QueryParams(query_items(params)),
            json=json_body,
            headers=headers,
            timeout=configuration.timeout,
        )
        try:
            response = await client.send(
                request,
                stream=True,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            if (
                operation.automatically_retryable
                and attempt < configuration.max_retries
            ):
                await _delay(configuration, attempt, None)
                continue
            raise TransportError(
                "The ParamPilot API stream could not be opened",
                operation.operation_id,
            ) from None
        if response.is_success or (allow_not_modified and response.status_code == 304):
            return response
        await response.aread()
        error = response_error(
            response,
            operation_id=operation.operation_id,
            secret=configuration.token,
        )
        await response.aclose()
        if (
            operation.automatically_retryable
            and error.retryable
            and attempt < configuration.max_retries
        ):
            await _delay(configuration, attempt, error.retry_after)
            continue
        raise error
    raise RuntimeError("unreachable retry state")

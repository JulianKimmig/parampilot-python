"""Async transport authentication, redirect, and contract-boundary tests."""

from __future__ import annotations

import httpx
import pytest

from parampilot import AsyncParamPilot
from parampilot.errors import (
    AuthenticationError,
    ConfigurationError,
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
    ResponseValidationError,
    RevisionConflictError,
    ServerError,
    UnsupportedMediaTypeError,
)
from tests.support import TOKEN, canonical_error


@pytest.mark.asyncio
async def test_authentication_error_preserves_safe_request_id() -> None:
    """Authentication failures must retain correlation without exposing auth data."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a canonical authentication failure.

        Args:
            request: Outbound SDK request.

        Returns:
            Canonical HTTP 401 response.

        """
        return httpx.Response(
            401,
            json=canonical_error("authentication_failed"),
            headers={"X-Request-ID": "req-safe-123"},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(AuthenticationError) as caught:
        await client.get_availability()

    assert caught.value.status_code == 401
    assert caught.value.request_id == "req-safe-123"
    assert TOKEN not in repr(caught.value)
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_redirects_are_not_followed_with_authorization() -> None:
    """A redirect response must never forward bearer credentials to another origin."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Capture and redirect the initial request.

        Args:
            request: Outbound SDK request.

        Returns:
            Cross-origin redirect response.

        """
        requests.append(request)
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.test/collect"},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ParamPilotHTTPError):
        await client.get_availability()

    assert len(requests) == 1
    assert requests[0].url.host == "example.test"
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_advanced_request_is_path_scoped_and_explicitly_untyped() -> None:
    """The escape hatch must retain auth safety while returning a raw response."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Capture one advanced request.

        Args:
            request: Outbound SDK request.

        Returns:
            Plain-text successful response.

        """
        requests.append(request)
        return httpx.Response(200, text="advanced", request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    response = await client.request(
        "GET",
        "/papi/v2/advanced/",
        params={"mode": "explicit"},
    )

    assert response.text == "advanced"
    assert requests[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Authorization" not in response.request.headers
    assert requests[0].url.params["mode"] == "explicit"
    with pytest.raises(ConfigurationError):
        await client.request("GET", "https://attacker.test/collect")
    assert len(requests) == 1
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_success_response_contract_violation_is_typed() -> None:
    """Malformed success JSON must raise a response-validation error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a success payload outside the Availability contract.

        Args:
            request: Outbound SDK request.

        Returns:
            Malformed successful response.

        """
        return httpx.Response(200, json={"status": "ok"}, request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ResponseValidationError) as caught:
        await client.get_availability()

    assert caught.value.operation_id == "getAvailability"
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "expected_type"),
    [
        (400, "invalid_request", InvalidRequestError),
        (403, "permission_denied", PermissionDeniedError),
        (404, "resource_not_found", NotFoundError),
        (409, "state_conflict", ConflictError),
        (409, "idempotency_key_reused", IdempotencyError),
        (409, "job_failed", JobError),
        (412, "revision_conflict", RevisionConflictError),
        (413, "payload_too_large", PayloadTooLargeError),
        (415, "unsupported_media_type", UnsupportedMediaTypeError),
        (422, "validation_failed", RequestValidationError),
        (423, "model_busy", LockedError),
        (428, "precondition_required", PreconditionRequiredError),
        (429, "rate_limited", RateLimitError),
        (503, "service_unavailable", ServerError),
    ],
)
async def test_status_catalog_maps_to_public_exception_taxonomy(
    status: int,
    code: str,
    expected_type: type[ParamPilotHTTPError],
) -> None:
    """Every canonical status family must expose its documented exception type.

    Args:
        status: Canonical HTTP status.
        code: Canonical machine error code.
        expected_type: Public exception class expected by callers.

    """

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return the parameterized canonical failure.

        Args:
            request: Outbound SDK request.

        Returns:
            Canonical error response.

        """
        return httpx.Response(
            status,
            json=canonical_error(code),
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        max_retries=0,
        http_client=http_client,
    )

    with pytest.raises(expected_type):
        await client.get_availability()

    await client.close()
    await http_client.aclose()

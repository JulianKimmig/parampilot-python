"""Sync/async modality parity and canonical transport error tests."""

from __future__ import annotations

import httpx
import pytest

from parampilot import AsyncParamPilot, ParamPilot
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
from parampilot.models import CampaignCreateRequest
from tests.support import TOKEN, availability_payload, canonical_error


@pytest.mark.asyncio
async def test_sync_client_works_while_an_asyncio_event_loop_is_running() -> None:
    """Native sync calls must not invoke or depend on the active asyncio loop."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return availability inside an async test's active loop.

        Args:
            request: Outbound SDK request.

        Returns:
            Successful compatibility response.

        """
        return httpx.Response(200, json=availability_payload(), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    response = client.get_availability()

    assert response.api_version == "2.0.0"
    client.close()
    http_client.close()  # noqa: ASYNC212 - verifies native sync use in active loop


@pytest.mark.asyncio
async def test_wrong_httpx_client_modality_fails_during_construction() -> None:
    """Callers must get a local error for a sync/async client type mismatch."""
    sync_http = httpx.Client(transport=httpx.MockTransport(lambda _: None))
    async_http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None))

    with pytest.raises(ConfigurationError, match="http_client"):
        ParamPilot(
            base_url="https://example.test",
            token=TOKEN,
            http_client=async_http,  # type: ignore[arg-type]
        )
    with pytest.raises(ConfigurationError, match="http_client"):
        AsyncParamPilot(
            base_url="https://example.test",
            token=TOKEN,
            http_client=sync_http,  # type: ignore[arg-type]
        )

    sync_http.close()  # noqa: ASYNC212 - intentional wrong-modality fixture
    await async_http.aclose()


@pytest.mark.asyncio
async def test_sync_and_async_canonical_error_fields_are_equivalent() -> None:
    """Both modalities must expose the same typed canonical error contract."""

    def response(request: httpx.Request) -> httpx.Response:
        """Build the shared canonical conflict fixture.

        Args:
            request: Outbound SDK request.

        Returns:
            Canonical idempotency conflict response.

        """
        return httpx.Response(
            409,
            json=canonical_error(
                "idempotency_key_reused",
                context={"key_state": "completed"},
            ),
            request=request,
        )

    async def async_handler(request: httpx.Request) -> httpx.Response:
        """Return the shared fixture through an async transport seam.

        Args:
            request: Outbound SDK request.

        Returns:
            Canonical conflict response.

        """
        return response(request)

    sync_http = httpx.Client(transport=httpx.MockTransport(response))
    async_http = httpx.AsyncClient(transport=httpx.MockTransport(async_handler))
    sync_client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=sync_http,
    )
    async_client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=async_http,
    )

    with pytest.raises(IdempotencyError) as sync_caught:
        sync_client.campaigns.create(CampaignCreateRequest(name="same"))
    with pytest.raises(IdempotencyError) as async_caught:
        await async_client.campaigns.create(CampaignCreateRequest(name="same"))

    sync_error = sync_caught.value
    async_error = async_caught.value
    assert type(sync_error) is type(async_error)
    assert sync_error.status_code == async_error.status_code
    assert sync_error.code == async_error.code
    assert sync_error.context == async_error.context
    assert sync_error.issues == async_error.issues
    assert sync_error.operation_id == async_error.operation_id
    assert sync_error.retryable == async_error.retryable
    sync_client.close()
    sync_http.close()  # noqa: ASYNC212 - parity is exercised in an active loop
    await async_client.close()
    await async_http.aclose()


@pytest.mark.parametrize(
    ("status", "code", "expected_type"),
    [
        (400, "invalid_request", InvalidRequestError),
        (401, "authentication_failed", AuthenticationError),
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
def test_sync_status_catalog_matches_public_exception_taxonomy(
    status: int,
    code: str,
    expected_type: type[ParamPilotHTTPError],
) -> None:
    """Every canonical status family must match the async exception type.

    Args:
        status: Canonical HTTP status.
        code: Canonical machine error code.
        expected_type: Public exception class expected by callers.

    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the parameterized canonical failure.

        Args:
            request: Outbound SDK request.

        Returns:
            Canonical error response.

        """
        return httpx.Response(status, json=canonical_error(code), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(expected_type):
        client.get_availability()

    client.close()
    http_client.close()


def test_sync_success_contract_violation_is_typed() -> None:
    """Malformed sync success JSON must raise the shared validation error."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a success payload outside the availability contract.

        Args:
            request: Outbound SDK request.

        Returns:
            Malformed successful response.

        """
        return httpx.Response(200, json={"status": "ok"}, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ResponseValidationError) as caught:
        client.get_availability()

    assert caught.value.operation_id == "getAvailability"
    client.close()
    http_client.close()

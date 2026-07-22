"""Behavior tests for async retries, idempotency, errors, and redaction."""

from __future__ import annotations

import json

import httpx
import pytest

from parampilot import AsyncParamPilot
from parampilot.errors import ParamPilotHTTPError, TrainingRequiredError
from parampilot.models import CampaignCreateRequest, CampaignResponse
from tests.support import (
    CAMPAIGN_ID,
    TOKEN,
    availability_payload,
    campaign_payload,
    canonical_error,
)


@pytest.mark.asyncio
async def test_safe_read_retries_retryable_server_error() -> None:
    """A safe GET must retry a canonical transient response within its budget."""
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return one transient error followed by a campaign.

        Args:
            request: Outbound SDK request.

        Returns:
            Retryable failure or success response.

        """
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(
                503,
                json=canonical_error("service_unavailable", retryable=True),
                request=request,
            )
        return httpx.Response(200, json=campaign_payload(), request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        max_retries=1,
        retry_backoff=0,
        http_client=http_client,
    )

    campaign = await client.campaigns.get(CAMPAIGN_ID)

    assert isinstance(campaign, CampaignResponse)
    assert requests == 2
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_keyed_mutation_reuses_one_key_and_body_across_transport_retry() -> None:
    """An idempotent mutation must preserve its generated key and exact JSON body."""
    keys: list[str] = []
    bodies: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Fail once at the external transport boundary, then succeed.

        Args:
            request: Outbound SDK request.

        Returns:
            Successful campaign response on the second call.

        Raises:
            httpx.ReadError: On the first attempt.

        """
        keys.append(request.headers["Idempotency-Key"])
        bodies.append(await request.aread())
        if len(keys) == 1:
            raise httpx.ReadError("connection reset", request=request)
        return httpx.Response(201, json=campaign_payload(), request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        max_retries=1,
        retry_backoff=0,
        http_client=http_client,
    )

    result = await client.campaigns.create(CampaignCreateRequest(name="Esterification"))

    assert result.name == "Esterification"
    assert len(keys) == 2
    assert keys[0] == keys[1]
    assert 8 <= len(keys[0]) <= 128
    assert bodies[0] == bodies[1]
    assert json.loads(bodies[0]) == {"name": "Esterification"}
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_canonical_errors_map_to_specific_safe_exception_types() -> None:
    """Status and error code must select typed exceptions without token leakage."""

    async def training_handler(request: httpx.Request) -> httpx.Response:
        """Return a structured training-required response.

        Args:
            request: Outbound SDK request.

        Returns:
            Canonical HTTP 409 response.

        """
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=["jobs.explicit-training"]),
                request=request,
            )
        payload = canonical_error(
            "training_required",
            context={"model_state": "stale", "unsafe_echo": TOKEN},
        )
        payload["error"]["message"] = f"Do not expose {TOKEN}"
        return httpx.Response(409, json=payload, request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(training_handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(TrainingRequiredError) as caught:
        await client.model_jobs.create_ask_job(CAMPAIGN_ID, n=1)

    assert caught.value.code == "training_required"
    assert caught.value.operation_id == "createAskJob"
    assert caught.value.context["model_state"] == "stale"
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)
    assert TOKEN not in repr(caught.value.context)
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_read_only_post_is_not_automatically_retried() -> None:
    """A POST query without an idempotency key must remain manual-retry only."""
    query_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        """Serve compatibility, then a retryable query failure.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability or service-unavailable response.

        """
        nonlocal query_requests
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=["experiments.effective"]),
                request=request,
            )
        query_requests += 1
        return httpx.Response(
            503,
            json=canonical_error("service_unavailable", retryable=True),
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        max_retries=3,
        retry_backoff=0,
        http_client=http_client,
    )

    with pytest.raises(ParamPilotHTTPError):
        await client.experiments.query_effective(CAMPAIGN_ID)

    assert query_requests == 1
    await client.close()
    await http_client.aclose()

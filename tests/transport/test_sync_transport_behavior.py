"""Behavior tests for native sync retries, errors, ownership, and safety."""

from __future__ import annotations

import json

import httpx
import pytest

from parampilot import ParamPilot
from parampilot.errors import (
    ConfigurationError,
    ParamPilotHTTPError,
    TrainingRequiredError,
)
from parampilot.models import CampaignCreateRequest, CampaignResponse
from tests.support import (
    CAMPAIGN_ID,
    TOKEN,
    availability_payload,
    campaign_payload,
    canonical_error,
)


def test_sync_safe_read_retries_retryable_server_error() -> None:
    """A native sync safe read must honor the shared bounded retry policy."""
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one canonical transient error followed by a campaign.

        Args:
            request: Outbound SDK request.

        Returns:
            Retryable failure or successful campaign response.

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

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        max_retries=1,
        retry_backoff=0,
        http_client=http_client,
    )

    campaign = client.campaigns.get(CAMPAIGN_ID)

    assert isinstance(campaign, CampaignResponse)
    assert requests == 2
    client.close()
    http_client.close()


def test_sync_keyed_mutation_reuses_identity_and_body_after_transport_error() -> None:
    """Sync retry must preserve request ID, idempotency key, and semantic body."""
    keys: list[str] = []
    request_ids: list[str] = []
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Fail the first external attempt and succeed the second.

        Args:
            request: Outbound SDK request.

        Returns:
            Successful campaign response on the second call.

        Raises:
            httpx.ReadError: On the first attempt.

        """
        keys.append(request.headers["Idempotency-Key"])
        request_ids.append(request.headers["X-Request-ID"])
        bodies.append(request.read())
        if len(keys) == 1:
            raise httpx.ReadError("connection reset", request=request)
        return httpx.Response(201, json=campaign_payload(), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        max_retries=1,
        retry_backoff=0,
        http_client=http_client,
    )

    result = client.campaigns.create(CampaignCreateRequest(name="Esterification"))

    assert result.name == "Esterification"
    assert len(set(keys)) == 1
    assert len(set(request_ids)) == 1
    assert bodies[0] == bodies[1]
    assert json.loads(bodies[0]) == {"name": "Esterification"}
    client.close()
    http_client.close()


def test_sync_training_required_error_matches_async_safe_context() -> None:
    """The shared canonical mapper must expose identical sync recovery context."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve compatibility and then reject Ask pending explicit training.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability or canonical training-required response.

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

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(TrainingRequiredError) as caught:
        client.model_jobs.create_ask_job(CAMPAIGN_ID, n=1)

    assert caught.value.operation_id == "createAskJob"
    assert caught.value.context["model_state"] == "stale"
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value.context)
    client.close()
    http_client.close()


def test_sync_advanced_request_is_scoped_sanitized_and_nonretrying() -> None:
    """The sync escape hatch must preserve the async auth and retry boundary."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Capture one advanced request and return successful text.

        Args:
            request: Outbound SDK request.

        Returns:
            Plain-text successful response.

        """
        requests.append(request)
        return httpx.Response(200, text="advanced", request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        max_retries=3,
        http_client=http_client,
    )

    response = client.request(
        "GET",
        "/papi/v2/advanced/",
        params={"mode": "explicit"},
    )

    assert response.text == "advanced"
    assert requests[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert "Authorization" not in response.request.headers
    with pytest.raises(ConfigurationError):
        client.request("GET", "https://attacker.test/collect")
    assert len(requests) == 1
    client.close()
    http_client.close()


def test_sync_redirect_is_not_followed_and_caller_pool_remains_open() -> None:
    """A sync client must refuse redirects and never close an injected pool."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return one cross-origin redirect while recording the request.

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

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ParamPilotHTTPError):
        client.get_availability()
    client.close()

    assert len(requests) == 1
    assert requests[0].url.host == "example.test"
    assert http_client.is_closed is False
    http_client.close()

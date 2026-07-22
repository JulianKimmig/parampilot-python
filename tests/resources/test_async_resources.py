"""Typed request and response tests for representative asynchronous resources."""

from __future__ import annotations

import json

import httpx
import pytest

from parampilot import AsyncParamPilot
from parampilot.models import (
    CampaignCreateRequest,
    CampaignResponse,
    ExperimentBatchResponse,
    ExtraData,
    ModelJobResponse,
    ShapResultsResponse,
)
from tests.support import (
    CAMPAIGN_ID,
    TOKEN,
    availability_payload,
    campaign_payload,
    model_job_payload,
)


@pytest.mark.asyncio
async def test_campaign_resource_serializes_typed_body_and_returns_metadata() -> None:
    """Campaign calls must use wire aliases and expose safe response metadata."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Capture campaign calls and return typed payloads.

        Args:
            request: Outbound SDK request.

        Returns:
            Campaign response with correlation and version headers.

        """
        requests.append(request)
        status = 201 if request.method == "POST" else 200
        return httpx.Response(
            status,
            json=campaign_payload(),
            headers={
                "ETag": '"campaign-v3"',
                "X-Request-ID": "req-campaign",
                "Set-Cookie": "private-session=must-not-escape",
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    created = await client.campaigns.create(
        CampaignCreateRequest(name="Esterification")
    )
    response = await client.campaigns.get_with_metadata(CAMPAIGN_ID)

    assert isinstance(created, CampaignResponse)
    assert isinstance(response.data, CampaignResponse)
    assert response.etag == '"campaign-v3"'
    assert response.require_etag() == '"campaign-v3"'
    assert response.request_id == "req-campaign"
    assert "set-cookie" not in response.headers
    assert requests[0].url.path == "/papi/v2/campaigns/"
    assert json.loads(await requests[0].aread()) == {"name": "Esterification"}
    assert requests[1].url.path == f"/papi/v2/campaigns/{CAMPAIGN_ID}/"
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_versioned_campaign_mutation_sends_precondition_and_idempotency() -> None:
    """Existing-resource mutations must send both concurrency safety headers."""
    captured: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        """Capture an additional-field replacement request.

        Args:
            request: Outbound SDK request.

        Returns:
            Updated campaign response.

        """
        nonlocal captured
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(),
                request=request,
            )
        captured = request
        return httpx.Response(200, json=campaign_payload(), request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    await client.campaigns.replace_additional_fields(
        CAMPAIGN_ID,
        ExtraData(fields=[]),
        if_match='"campaign-v3"',
        idempotency_key="replace-fields-123",
    )

    assert captured is not None
    assert captured.method == "PUT"
    assert captured.headers["If-Match"] == '"campaign-v3"'
    assert captured.headers["Idempotency-Key"] == "replace-fields-123"
    assert json.loads(await captured.aread()) == {"fields": []}
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_ask_and_predict_never_call_training_but_train_model_does() -> None:
    """Only the explicitly train-named method may target the training operation."""
    requests: list[tuple[str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Serve capabilities and capture each model-job submission.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability or typed job response.

        """
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=["jobs.explicit-training"]),
                request=request,
            )
        body = json.loads(await request.aread())
        requests.append((request.url.path, body))
        if "training-jobs" in request.url.path:
            kind = "train"
        elif "prediction-jobs" in request.url.path:
            kind = "predict"
        else:
            kind = "ask"
        return httpx.Response(
            202,
            json=model_job_payload(kind=kind),
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    ask = await client.model_jobs.create_ask_job(CAMPAIGN_ID, n=2)
    predict = await client.model_jobs.create_prediction_job(
        CAMPAIGN_ID,
        rows=[{"temperature": 80.0}],
    )

    assert isinstance(ask, ModelJobResponse)
    assert isinstance(predict, ModelJobResponse)
    assert all("training-jobs" not in path for path, _ in requests)
    assert requests[0][1] == {"n": 2}
    assert requests[1][1] == {"rows": [{"temperature": 80.0}]}

    trained = await client.model_jobs.train_model(CAMPAIGN_ID)

    assert isinstance(trained, ModelJobResponse)
    assert requests[-1][0].endswith("/model/training-jobs/")
    assert requests[-1][1] == {}
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_experiment_file_import_is_bounded_multipart_and_typed() -> None:
    """File import must send explicit bytes/media metadata and validate its result."""
    captured: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        """Capture multipart upload and return an empty atomic result.

        Args:
            request: Outbound SDK request.

        Returns:
            Typed batch response.

        """
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"items": []}, request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = await client.experiments.import_file(
        CAMPAIGN_ID,
        b"labcode,temperature\nex-1,80\n",
        filename="experiments.csv",
        content_type="text/csv",
    )

    assert isinstance(result, ExperimentBatchResponse)
    assert captured is not None
    assert captured.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    body = await captured.aread()
    assert b"experiments.csv" in body
    assert b"labcode,temperature" in body
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_conditional_shap_read_returns_none_for_not_modified() -> None:
    """Conditional model-artifact reads must expose HTTP 304 without decoding JSON."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Serve capability handshake then conditional artifact responses.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability, artifact, or not-modified response.

        """
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=["artifacts.shap-results"]),
                request=request,
            )
        requests.append(request)
        if request.headers.get("If-None-Match"):
            return httpx.Response(304, request=request)
        return httpx.Response(
            200,
            json={
                "campaign_id": CAMPAIGN_ID,
                "model_revision": "model-v1",
                "generated_at": "2026-07-14T12:00:00Z",
                "shap_results": {"temperature": 0.75},
            },
            headers={"ETag": '"shap-v1"'},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    artifact = await client.model_artifacts.get_shap_results(CAMPAIGN_ID)
    unchanged = await client.model_artifacts.get_shap_results(
        CAMPAIGN_ID,
        if_none_match='"shap-v1"',
    )

    assert isinstance(artifact, ShapResultsResponse)
    assert unchanged is None
    assert requests[-1].headers["If-None-Match"] == '"shap-v1"'
    await client.close()
    await http_client.aclose()

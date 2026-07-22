"""Typed request and response behavior for representative sync resources."""

from __future__ import annotations

import json

import httpx

from parampilot import ParamPilot
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


def test_sync_campaign_serialization_metadata_and_version_headers() -> None:
    """Sync campaign calls must share typed bodies, ETags, and safe headers."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Capture campaign calls and return typed payloads.

        Args:
            request: Outbound SDK request.

        Returns:
            Campaign response with correlation and version headers.

        """
        requests.append(request)
        return httpx.Response(
            201 if request.method == "POST" else 200,
            json=campaign_payload(),
            headers={
                "ETag": '"campaign-v3"',
                "X-Request-ID": "req-campaign",
                "Set-Cookie": "private-session=must-not-escape",
            },
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    created = client.campaigns.create(CampaignCreateRequest(name="Esterification"))
    response = client.campaigns.get_with_metadata(CAMPAIGN_ID)

    assert isinstance(created, CampaignResponse)
    assert isinstance(response.data, CampaignResponse)
    assert response.require_etag() == '"campaign-v3"'
    assert response.request_id == "req-campaign"
    assert "set-cookie" not in response.headers
    assert json.loads(requests[0].read()) == {"name": "Esterification"}
    client.close()
    http_client.close()


def test_sync_versioned_mutation_sends_precondition_and_idempotency() -> None:
    """Sync existing-resource mutations must send both safety headers."""
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve compatibility and capture a replacement mutation.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability or updated campaign response.

        """
        nonlocal captured
        if request.url.path.endswith("/availability/"):
            return httpx.Response(200, json=availability_payload(), request=request)
        captured = request
        return httpx.Response(200, json=campaign_payload(), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    client.campaigns.replace_additional_fields(
        CAMPAIGN_ID,
        ExtraData(fields=[]),
        if_match='"campaign-v3"',
        idempotency_key="replace-fields-123",
    )

    assert captured is not None
    assert captured.headers["If-Match"] == '"campaign-v3"'
    assert captured.headers["Idempotency-Key"] == "replace-fields-123"
    assert json.loads(captured.read()) == {"fields": []}
    client.close()
    http_client.close()


def test_sync_ask_predict_and_explicit_train_use_distinct_operations() -> None:
    """Only the sync train-named method may target the training operation."""
    requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
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
        body = json.loads(request.read())
        requests.append((request.url.path, body))
        if "training-jobs" in request.url.path:
            kind = "train"
        elif "prediction-jobs" in request.url.path:
            kind = "predict"
        else:
            kind = "ask"
        return httpx.Response(202, json=model_job_payload(kind=kind), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    ask = client.model_jobs.create_ask_job(CAMPAIGN_ID, n=2)
    predict = client.model_jobs.create_prediction_job(
        CAMPAIGN_ID,
        rows=[{"temperature": 80.0}],
    )

    assert isinstance(ask, ModelJobResponse)
    assert isinstance(predict, ModelJobResponse)
    assert all("training-jobs" not in path for path, _ in requests)
    assert requests[0][1] == {"n": 2}
    assert requests[1][1] == {"rows": [{"temperature": 80.0}]}

    trained = client.model_jobs.train_model(CAMPAIGN_ID)

    assert isinstance(trained, ModelJobResponse)
    assert requests[-1][0].endswith("/model/training-jobs/")
    assert requests[-1][1] == {}
    client.close()
    http_client.close()


def test_sync_experiment_import_is_bounded_multipart_and_typed() -> None:
    """Sync file import must preserve explicit bytes/media and typed results."""
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        """Capture multipart upload and return an empty atomic result.

        Args:
            request: Outbound SDK request.

        Returns:
            Typed batch response.

        """
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"items": []}, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = client.experiments.import_file(
        CAMPAIGN_ID,
        b"labcode,temperature\nex-1,80\n",
        filename="experiments.csv",
        content_type="text/csv",
    )

    assert isinstance(result, ExperimentBatchResponse)
    assert captured is not None
    assert captured.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    body = captured.read()
    assert b"experiments.csv" in body
    assert b"labcode,temperature" in body
    client.close()
    http_client.close()


def test_sync_conditional_shap_read_returns_none_for_not_modified() -> None:
    """Sync conditional artifact reads must expose HTTP 304 without decoding."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
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

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    artifact = client.model_artifacts.get_shap_results(CAMPAIGN_ID)
    unchanged = client.model_artifacts.get_shap_results(
        CAMPAIGN_ID,
        if_none_match='"shap-v1"',
    )

    assert isinstance(artifact, ShapResultsResponse)
    assert unchanged is None
    assert requests[-1].headers["If-None-Match"] == '"shap-v1"'
    client.close()
    http_client.close()

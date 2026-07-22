"""Native async/sync resource integration tests for waitable model jobs."""

from __future__ import annotations

import httpx
import pytest

from parampilot import ConfigurationError, ParamPilot
from parampilot.models import ModelJobResponse, PredictResult, TrainResult
from tests.support import (
    CAMPAIGN_ID,
    JOB_ID,
    TOKEN,
    availability_payload,
    job_observation_payload,
    job_result_payload,
    model_job_payload,
)

JOB_CAPABILITIES = ["jobs.observations", "jobs.explicit-training"]


def test_sync_waiting_submission_validates_timing_before_any_request() -> None:
    """Invalid wait controls must never submit a potentially billable Train job."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record an HTTP request that must remain unreachable.

        Args:
            request: Unexpected outbound SDK request.

        Returns:
            Compatibility response allowing an unsafe implementation to continue.

        """
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json=availability_payload(capabilities=JOB_CAPABILITIES),
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ConfigurationError, match="poll_interval"):
        client.model_jobs.train_model(CAMPAIGN_ID, wait=True, poll_interval=0)

    assert paths == []
    client.close()
    http_client.close()


def test_sync_train_model_wait_true_submits_once_then_returns_train_result() -> None:
    """Sync explicit training may submit once and block for its typed result."""
    paths: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve explicit Train submission, observation, and result.

        Args:
            request: Outbound SDK request.

        Returns:
            Typed public response for the requested operation.

        """
        paths.append((request.method, request.url.path))
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=JOB_CAPABILITIES),
                request=request,
            )
        if request.url.path.endswith("/training-jobs/"):
            return httpx.Response(
                202,
                json=model_job_payload(kind="train"),
                request=request,
            )
        if request.url.path.endswith("/observation/"):
            return httpx.Response(
                200,
                json=job_observation_payload(status="done"),
                request=request,
            )
        return httpx.Response(
            200,
            json=job_result_payload(kind="train"),
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = client.model_jobs.train_model(
        CAMPAIGN_ID,
        wait=True,
        timeout=10,
        poll_interval=0.05,
    )

    assert isinstance(result, TrainResult)
    assert sum(path.endswith("/training-jobs/") for _, path in paths) == 1
    assert paths[-1][1].endswith("/result/")
    client.close()
    http_client.close()


def test_sync_predict_wait_true_never_targets_training_operation() -> None:
    """Waitable Predict must submit only Predict and return its typed result."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve Predict submission, terminal observation, and result.

        Args:
            request: Outbound SDK request.

        Returns:
            Typed public response for the requested operation.

        """
        paths.append(request.url.path)
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=JOB_CAPABILITIES),
                request=request,
            )
        if request.url.path.endswith("/prediction-jobs/"):
            return httpx.Response(
                202,
                json=model_job_payload(kind="predict"),
                request=request,
            )
        if request.url.path.endswith("/observation/"):
            return httpx.Response(
                200,
                json=job_observation_payload(status="done", kind="predict"),
                request=request,
            )
        return httpx.Response(
            200,
            json=job_result_payload(kind="predict"),
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = client.model_jobs.create_prediction_job(
        CAMPAIGN_ID,
        rows=[{"temperature": 42.0}],
        wait=True,
        timeout=10,
        poll_interval=0.05,
    )

    assert isinstance(result, PredictResult)
    assert any(path.endswith("/prediction-jobs/") for path in paths)
    assert not any("training-jobs" in path for path in paths)
    client.close()
    http_client.close()


def test_default_submission_behavior_remains_nonwaiting_and_backward_compatible() -> (
    None
):
    """Omitting wait must still return the accepted ModelJob response immediately."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve capability handshake and one Ask submission.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability or queued Ask job.

        """
        paths.append(request.url.path)
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=JOB_CAPABILITIES),
                request=request,
            )
        return httpx.Response(202, json=model_job_payload(kind="ask"), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    submitted = client.model_jobs.create_ask_job(CAMPAIGN_ID, n=1)

    assert isinstance(submitted, ModelJobResponse)
    assert not any(path.endswith("/observation/") for path in paths)
    client.close()
    http_client.close()


def test_observation_metadata_exposes_safe_retry_after_guidance() -> None:
    """Metadata-aware observation reads must retain only safe polling headers."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve compatibility and an observation with safe/unsafe headers.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability or observation response.

        """
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(capabilities=JOB_CAPABILITIES),
                request=request,
            )
        return httpx.Response(
            200,
            json=job_observation_payload(status="queued"),
            headers={"Retry-After": "3", "Set-Cookie": "private=secret"},
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    response = client.model_jobs.get_observation_with_metadata(CAMPAIGN_ID, JOB_ID)

    assert response.headers["retry-after"] == "3"
    assert "set-cookie" not in response.headers
    client.close()
    http_client.close()

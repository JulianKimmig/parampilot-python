"""Asynchronous waitable model-job resource integration tests."""

from __future__ import annotations

import httpx
import pytest

from parampilot import AsyncParamPilot, ConfigurationError
from parampilot.models import AskResult, TrainResult
from tests.jobs.test_job_resources import JOB_CAPABILITIES
from tests.support import (
    CAMPAIGN_ID,
    JOB_ID,
    TOKEN,
    availability_payload,
    job_observation_payload,
    job_result_payload,
    model_job_payload,
)


@pytest.mark.asyncio
async def test_async_waiting_submission_validates_timing_before_any_request() -> None:
    """Async invalid wait controls must fail before explicit Train submission."""
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
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

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ConfigurationError, match="timeout"):
        await client.model_jobs.train_model(CAMPAIGN_ID, wait=True, timeout=0)

    assert paths == []
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_async_wait_polls_observations_and_never_submits_training() -> None:
    """A standalone async wait must only observe and retrieve an existing job."""
    statuses = iter(["queued", "running", "done"])
    paths: list[tuple[str, str]] = []
    delivered: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Serve compatibility, state transitions, and a Train result.

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
        if request.url.path.endswith("/observation/"):
            return httpx.Response(
                200,
                json=job_observation_payload(status=next(statuses)),
                headers={"Retry-After": "0.05"},
                request=request,
            )
        return httpx.Response(
            200,
            json=job_result_payload(kind="train"),
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = await client.model_jobs.wait(
        CAMPAIGN_ID,
        JOB_ID,
        timeout=10,
        poll_interval=0.05,
        on_progress=lambda value: delivered.append(value.status.value),
    )

    assert isinstance(result, TrainResult)
    assert delivered == ["queued", "running", "done"]
    assert not any("training-jobs" in path for _, path in paths)
    assert [method for method, path in paths if path.endswith("/observation/")] == [
        "GET",
        "GET",
        "GET",
    ]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_async_train_model_wait_true_submits_once_and_awaits_result() -> None:
    """Async explicit training may submit once and await its typed result."""
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Serve explicit Train submission, observation, and result.

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

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = await client.model_jobs.train_model(
        CAMPAIGN_ID,
        wait=True,
        timeout=10,
        poll_interval=0.05,
    )

    assert isinstance(result, TrainResult)
    assert sum(path.endswith("/training-jobs/") for path in paths) == 1
    assert paths[-1].endswith("/result/")
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_async_ask_wait_true_never_targets_training_operation() -> None:
    """Waitable Ask must submit only Ask and return the concrete Ask result."""
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        """Serve Ask submission, terminal observation, and result.

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
        if request.url.path.endswith("/ask-jobs/"):
            return httpx.Response(
                202,
                json=model_job_payload(kind="ask"),
                request=request,
            )
        if request.url.path.endswith("/observation/"):
            return httpx.Response(
                200,
                json=job_observation_payload(status="done", kind="ask"),
                request=request,
            )
        return httpx.Response(
            200,
            json=job_result_payload(kind="ask"),
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = await client.model_jobs.create_ask_job(
        CAMPAIGN_ID,
        n=2,
        wait=True,
        timeout=10,
        poll_interval=0.05,
    )

    assert isinstance(result, AskResult)
    assert any(path.endswith("/ask-jobs/") for path in paths)
    assert not any("training-jobs" in path for path in paths)
    await client.close()
    await http_client.aclose()

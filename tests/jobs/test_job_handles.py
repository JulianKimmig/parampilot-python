"""Reconstructable token-free typed job-handle tests."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from parampilot import (
    AskJobHandle,
    AsyncParamPilot,
    ParamPilot,
    PredictJobHandle,
    TrainingJobHandle,
)
from parampilot.errors import ResponseValidationError
from parampilot.job_handles import job_handle
from parampilot.models import AskResult, ModelJobResponse, TrainResult
from tests.support import (
    CAMPAIGN_ID,
    JOB_ID,
    TOKEN,
    availability_payload,
    job_observation_payload,
    job_result_payload,
    model_job_payload,
)


@pytest.mark.parametrize(
    ("kind", "expected_type"),
    [
        ("train", TrainingJobHandle),
        ("ask", AskJobHandle),
        ("predict", PredictJobHandle),
    ],
)
def test_job_response_converts_to_discriminated_serializable_handle(
    kind: str,
    expected_type: type[TrainingJobHandle | AskJobHandle | PredictJobHandle],
) -> None:
    """Every submitted job kind must produce a reconstructable pure-data handle.

    Args:
        kind: Public job discriminator.
        expected_type: Matching concrete handle class.

    """
    response = ModelJobResponse.model_validate(model_job_payload(kind=kind))

    handle = job_handle(response)
    encoded = handle.model_dump_json()

    assert isinstance(handle, expected_type)
    assert json.loads(encoded) == {
        "campaign_id": CAMPAIGN_ID,
        "job_id": JOB_ID,
        "kind": kind,
    }
    assert TOKEN not in encoded
    assert "client" not in encoded
    assert "http" not in encoded


def test_concrete_handle_rejects_a_mismatched_job_kind() -> None:
    """A concrete handle must preserve its discriminated result contract."""
    with pytest.raises(ValidationError):
        TrainingJobHandle(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            kind="ask",  # type: ignore[arg-type]
        )


def test_concrete_handle_rejects_a_mismatched_terminal_result_kind() -> None:
    """A reconstructed concrete handle must validate the fetched result kind."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve a mismatched Ask result for a declared Train handle.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability, terminal observation, or mismatched result.

        """
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(
                    capabilities=["jobs.observations", "jobs.explicit-training"]
                ),
                request=request,
            )
        if request.url.path.endswith("/observation/"):
            return httpx.Response(
                200,
                json=job_observation_payload(status="done", kind="train"),
                request=request,
            )
        return httpx.Response(200, json=job_result_payload(kind="ask"), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )
    handle = TrainingJobHandle(campaign_id=CAMPAIGN_ID, job_id=JOB_ID)

    with pytest.raises(ResponseValidationError, match="result kind"):
        handle.wait(client, timeout=10, poll_interval=1)

    client.close()
    http_client.close()


def test_sync_handle_can_refresh_wait_cancel_and_fetch_typed_result() -> None:
    """A sync handle must feed client operations without retaining the client."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve handle operations from public HTTP fixtures.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability, observation, result, or cancellation response.

        """
        paths.append(request.url.path)
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(
                    capabilities=["jobs.observations", "jobs.explicit-training"]
                ),
                request=request,
            )
        if request.url.path.endswith("/cancel/"):
            return httpx.Response(
                200, json=model_job_payload(kind="train"), request=request
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
    handle = TrainingJobHandle(campaign_id=CAMPAIGN_ID, job_id=JOB_ID)

    observation = handle.refresh(client)
    result = handle.wait(client, timeout=10, poll_interval=1)
    fetched = handle.result(client)
    canceled = handle.cancel(client, idempotency_key="cancel-handle-1")

    assert observation.status.value == "done"
    assert isinstance(result, TrainResult)
    assert isinstance(fetched, TrainResult)
    assert canceled.kind.value == "train"
    assert all("training-jobs" not in path for path in paths)
    client.close()
    http_client.close()


@pytest.mark.asyncio
async def test_async_ask_handle_preserves_concrete_result_type() -> None:
    """An async Ask handle must await observations and return an Ask result."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Serve async handle observations and results.

        Args:
            request: Outbound SDK request.

        Returns:
            Availability, observation, or Ask result.

        """
        if request.url.path.endswith("/availability/"):
            return httpx.Response(
                200,
                json=availability_payload(
                    capabilities=["jobs.observations", "jobs.explicit-training"]
                ),
                request=request,
            )
        if request.url.path.endswith("/observation/"):
            return httpx.Response(
                200,
                json=job_observation_payload(status="done", kind="ask"),
                request=request,
            )
        return httpx.Response(200, json=job_result_payload(kind="ask"), request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )
    handle = AskJobHandle(campaign_id=CAMPAIGN_ID, job_id=JOB_ID)

    result = await handle.wait_async(client, timeout=10, poll_interval=1)

    assert isinstance(result, AskResult)
    await client.close()
    await http_client.aclose()

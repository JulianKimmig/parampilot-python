"""Asynchronous explicit upload-train-ask workflow behavior and recovery tests."""

from __future__ import annotations

import httpx
import pytest

from parampilot import (
    AddExperimentsTrainAndAskCheckpoint,
    AddExperimentsTrainAndAskError,
    AsyncParamPilot,
    WorkflowProgressCallbackError,
)
from parampilot.workflow_models import (
    WorkflowEventStatus,
    WorkflowPhase,
    WorkflowProgressEvent,
    WorkflowStage,
)
from tests.support import CAMPAIGN_ID, TOKEN
from tests.workflows.fixtures import EXPERIMENTS
from tests.workflows.support import WorkflowScenario
from tests.workflows.test_sync_workflow import FAILURE_STAGES, IDEMPOTENCY_KEY


def _client(
    scenario: WorkflowScenario,
    *,
    max_retries: int = 0,
) -> tuple[AsyncParamPilot, httpx.AsyncClient]:
    """Create a native async client bound to one workflow scenario.

    Args:
        scenario: Stateful fake public API.
        max_retries: Transport retry count.

    Returns:
        SDK client and caller-owned HTTPX client.

    """
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(scenario.handle_async)
    )
    return (
        AsyncParamPilot(
            base_url="https://example.test",
            token=TOKEN,
            max_retries=max_retries,
            http_client=http_client,
        ),
        http_client,
    )


@pytest.mark.asyncio
async def test_async_workflow_awaits_callbacks_and_returns_typed_suggestions() -> None:
    """One awaited call must expose every explicit workflow phase."""
    scenario = WorkflowScenario()
    client, http_client = _client(scenario)
    phases: list[WorkflowPhase] = []

    async def callback(event: WorkflowProgressEvent) -> None:
        """Record one asynchronously delivered workflow event.

        Args:
            event: Typed workflow progress event.

        """
        phases.append(event.phase)

    result = await client.workflows.add_experiments_train_and_ask(
        CAMPAIGN_ID,
        EXPERIMENTS,
        n=1,
        idempotency_key=IDEMPOTENCY_KEY,
        timeout=10,
        poll_interval=0.01,
        on_progress=callback,
    )

    assert result.checkpoint.stage is WorkflowStage.completed
    assert [item.labcode for item in result.suggested_experiments] == ["candidate-001"]
    assert WorkflowPhase.upload in phases
    assert WorkflowPhase.training in phases
    assert WorkflowPhase.ask in phases
    assert WorkflowPhase.suggestions in phases
    assert phases[-1] is WorkflowPhase.terminal
    assert scenario.count("train_submit") == 1
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_phase"), FAILURE_STAGES
)
async def test_async_workflow_failure_matrix_preserves_exact_checkpoint(
    failure: str,
    expected_stage: WorkflowStage,
    expected_phase: WorkflowPhase,
) -> None:
    """Every remote failure must expose the last completed async stage.

    Args:
        failure: Injected operation label.
        expected_stage: Last completed checkpoint stage.
        expected_phase: Public phase that failed.

    """
    scenario = WorkflowScenario(fail_at=failure)
    client, http_client = _client(scenario)

    with pytest.raises(AddExperimentsTrainAndAskError) as caught:
        await client.workflows.add_experiments_train_and_ask(
            CAMPAIGN_ID,
            EXPERIMENTS,
            n=1,
            idempotency_key=IDEMPOTENCY_KEY,
            timeout=10,
            poll_interval=0.01,
        )

    assert caught.value.checkpoint.stage is expected_stage
    assert caught.value.failed_phase is expected_phase
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_async_resume_waits_existing_ask_after_lost_result_response() -> None:
    """Async resume must not re-upload, retrain, or resubmit an accepted Ask."""
    scenario = WorkflowScenario(lose_response_once_at="ask_result")
    first_client, first_http = _client(scenario)

    with pytest.raises(AddExperimentsTrainAndAskError) as caught:
        await first_client.workflows.add_experiments_train_and_ask(
            CAMPAIGN_ID,
            EXPERIMENTS,
            n=1,
            idempotency_key=IDEMPOTENCY_KEY,
            timeout=10,
            poll_interval=0.01,
        )
    serialized = caught.value.checkpoint.model_dump_json()
    await first_client.close()
    await first_http.aclose()

    checkpoint = AddExperimentsTrainAndAskCheckpoint.model_validate_json(serialized)
    resumed_client, resumed_http = _client(scenario)
    result = await resumed_client.workflows.resume_add_experiments_train_and_ask(
        checkpoint,
        EXPERIMENTS,
        n=1,
        timeout=10,
        poll_interval=0.01,
    )

    assert result.checkpoint.stage is WorkflowStage.completed
    assert scenario.count("batch") == 1
    assert scenario.count("train_submit") == 1
    assert scenario.count("ask_submit") == 1
    assert scenario.count("ask_result") == 2
    await resumed_client.close()
    await resumed_http.aclose()


@pytest.mark.asyncio
async def test_async_job_progress_failure_never_cancels_or_resubmits_training() -> None:
    """Awaitable callback failure must leave Train recoverable by its job ID."""
    scenario = WorkflowScenario()
    client, http_client = _client(scenario)

    async def callback(event: WorkflowProgressEvent) -> None:
        """Fail on the first validated Train observation.

        Args:
            event: Typed workflow progress event.

        Raises:
            RuntimeError: On Train job progress.

        """
        if (
            event.phase is WorkflowPhase.training
            and event.status is WorkflowEventStatus.progress
        ):
            raise RuntimeError("progress sink unavailable")

    with pytest.raises(WorkflowProgressCallbackError) as caught:
        await client.workflows.add_experiments_train_and_ask(
            CAMPAIGN_ID,
            EXPERIMENTS,
            n=1,
            idempotency_key=IDEMPOTENCY_KEY,
            timeout=10,
            poll_interval=0.01,
            on_progress=callback,
        )

    assert caught.value.checkpoint.stage is WorkflowStage.training_submitted
    assert scenario.count("train_submit") == 1
    assert scenario.count("train_result") == 0
    result = await client.workflows.resume_add_experiments_train_and_ask(
        caught.value.checkpoint,
        EXPERIMENTS,
        n=1,
        timeout=10,
        poll_interval=0.01,
    )
    assert result.checkpoint.stage is WorkflowStage.completed
    assert scenario.count("train_submit") == 1
    await client.close()
    await http_client.aclose()

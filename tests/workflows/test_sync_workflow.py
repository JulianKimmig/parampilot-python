"""Synchronous explicit upload-train-ask workflow behavior and recovery tests."""

from __future__ import annotations

import re

import httpx
import pytest

from parampilot import (
    AddExperimentsTrainAndAskError,
    AddExperimentsTrainAndAskResult,
    ParamPilot,
)
from parampilot.workflow_models import (
    WorkflowPhase,
    WorkflowProgressCallback,
    WorkflowStage,
)
from tests.support import CAMPAIGN_ID, TOKEN
from tests.workflows.fixtures import (
    ASK_JOB_ID,
    EXPERIMENTS,
    SUGGESTION_ID,
    TRAIN_JOB_ID,
)
from tests.workflows.support import WorkflowScenario

IDEMPOTENCY_KEY = "workflow-user-stable-0001"
FAILURE_STAGES = [
    ("batch", WorkflowStage.initialized, WorkflowPhase.upload),
    ("train_submit", WorkflowStage.experiments_upserted, WorkflowPhase.training),
    ("train_observe", WorkflowStage.training_submitted, WorkflowPhase.training),
    ("train_result", WorkflowStage.training_submitted, WorkflowPhase.training),
    ("ask_submit", WorkflowStage.training_completed, WorkflowPhase.ask),
    ("ask_observe", WorkflowStage.ask_submitted, WorkflowPhase.ask),
    ("ask_result", WorkflowStage.ask_submitted, WorkflowPhase.ask),
    ("suggestions", WorkflowStage.ask_completed, WorkflowPhase.suggestions),
]


def _client(
    scenario: WorkflowScenario, *, max_retries: int = 0
) -> tuple[ParamPilot, httpx.Client]:
    """Create a native sync client bound to one workflow scenario.

    Args:
        scenario: Stateful fake public API.
        max_retries: Transport retry count.

    Returns:
        SDK client and caller-owned HTTPX client.

    """
    http_client = httpx.Client(transport=httpx.MockTransport(scenario.handle))
    return (
        ParamPilot(
            base_url="https://example.test",
            token=TOKEN,
            max_retries=max_retries,
            http_client=http_client,
        ),
        http_client,
    )


def _run(
    client: ParamPilot,
    *,
    on_progress: WorkflowProgressCallback | None = None,
) -> AddExperimentsTrainAndAskResult:
    """Run the standard synchronous workflow fixture.

    Args:
        client: Open native synchronous SDK client.
        on_progress: Optional progress callback under test.

    Returns:
        Typed composite workflow result.

    """
    return client.workflows.add_experiments_train_and_ask(
        CAMPAIGN_ID,
        EXPERIMENTS,
        n=1,
        idempotency_key=IDEMPOTENCY_KEY,
        timeout=10,
        poll_interval=0.01,
        on_progress=on_progress,
    )


def test_sync_workflow_executes_visible_order_and_returns_typed_suggestions() -> None:
    """One blocking call must upload, explicitly train, Ask, and return rows."""
    scenario = WorkflowScenario()
    client, http_client = _client(scenario)
    events = []

    result = _run(client, on_progress=events.append)

    assert [
        call.operation for call in scenario.calls if call.operation != "availability"
    ] == [
        "batch",
        "train_submit",
        "train_observe",
        "train_result",
        "ask_submit",
        "ask_observe",
        "ask_result",
        "suggestions",
    ]
    assert result.checkpoint.stage is WorkflowStage.completed
    assert str(result.checkpoint.training_job_id) == TRAIN_JOB_ID
    assert str(result.checkpoint.ask_job_id) == ASK_JOB_ID
    assert [str(item.id) for item in result.suggested_experiments] == [SUGGESTION_ID]
    assert result.suggested_experiments[0].inputs == {"temperature": 91.0}
    assert any(event.phase is WorkflowPhase.training for event in events)
    assert any(event.phase is WorkflowPhase.terminal for event in events)
    assert all(TOKEN not in event.model_dump_json() for event in events)
    assert IDEMPOTENCY_KEY not in result.checkpoint.model_dump_json()
    key_values = result.checkpoint.idempotency_keys.model_dump().values()
    assert all(re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key) for key in key_values)
    assert scenario.keys("batch") == [result.checkpoint.idempotency_keys.experiments]
    assert scenario.keys("train_submit") == [
        result.checkpoint.idempotency_keys.training
    ]
    assert scenario.keys("ask_submit") == [result.checkpoint.idempotency_keys.ask]
    client.close()
    http_client.close()


def test_workflow_public_methods_all_make_training_visible_in_their_names() -> None:
    """No ambiguous workflow alias may hide an explicit training submission."""
    scenario = WorkflowScenario()
    client, http_client = _client(scenario)

    methods = {
        name
        for name in dir(client.workflows)
        if not name.startswith("_") and callable(getattr(client.workflows, name))
    }

    assert methods == {
        "add_experiments_train_and_ask",
        "resume_add_experiments_train_and_ask",
    }
    assert all("train" in name for name in methods)
    client.close()
    http_client.close()


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_phase"), FAILURE_STAGES
)
def test_sync_workflow_failure_matrix_preserves_exact_checkpoint(
    failure: str,
    expected_stage: WorkflowStage,
    expected_phase: WorkflowPhase,
) -> None:
    """Every remote failure must expose the last completed synchronous stage.

    Args:
        failure: Injected operation label.
        expected_stage: Last completed checkpoint stage.
        expected_phase: Public phase that failed.

    """
    scenario = WorkflowScenario(fail_at=failure)
    client, http_client = _client(scenario)

    with pytest.raises(AddExperimentsTrainAndAskError) as caught:
        _run(client)

    assert caught.value.checkpoint.stage is expected_stage
    assert caught.value.failed_phase is expected_phase
    assert caught.value.__cause__ is not None
    assert TOKEN not in caught.value.checkpoint.model_dump_json()
    client.close()
    http_client.close()

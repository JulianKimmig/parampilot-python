"""Synchronous workflow restart, callback, race, and validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from parampilot import (
    AddExperimentsTrainAndAskCheckpoint,
    AddExperimentsTrainAndAskError,
    ConfigurationError,
    TrainingRequiredError,
    WorkflowProgressCallbackError,
    WorkflowResumeMismatchError,
)
from parampilot.workflow_models import (
    WorkflowPhase,
    WorkflowProgressEvent,
    WorkflowStage,
)
from tests.support import CAMPAIGN_ID
from tests.workflows.fixtures import EXPERIMENTS
from tests.workflows.support import WorkflowScenario
from tests.workflows.test_sync_workflow import IDEMPOTENCY_KEY, _client, _run


def test_sync_process_restart_replays_lost_training_submission_without_reupload() -> (
    None
):
    """A serialized checkpoint must replay one accepted Train key after restart."""
    scenario = WorkflowScenario(lose_response_once_at="train_submit")
    first_client, first_http = _client(scenario)

    with pytest.raises(AddExperimentsTrainAndAskError) as caught:
        _run(first_client)
    serialized = caught.value.checkpoint.model_dump_json()
    first_client.close()
    first_http.close()

    checkpoint = AddExperimentsTrainAndAskCheckpoint.model_validate_json(serialized)
    resumed_client, resumed_http = _client(scenario)
    result = resumed_client.workflows.resume_add_experiments_train_and_ask(
        checkpoint,
        EXPERIMENTS,
        n=1,
        timeout=10,
        poll_interval=0.01,
    )

    assert result.checkpoint.stage is WorkflowStage.completed
    assert scenario.count("batch") == 1
    assert scenario.count("train_submit") == 2
    assert len(set(scenario.keys("train_submit"))) == 1
    resumed_client.close()
    resumed_http.close()


def test_sync_resume_rejects_mismatched_input_before_http() -> None:
    """Changed rows, n, or base key must never reuse another workflow checkpoint."""
    scenario = WorkflowScenario(lose_response_once_at="train_submit")
    client, http_client = _client(scenario)
    with pytest.raises(AddExperimentsTrainAndAskError) as caught:
        _run(client)
    calls_before = len(scenario.calls)

    with pytest.raises(WorkflowResumeMismatchError, match="fingerprint"):
        client.workflows.resume_add_experiments_train_and_ask(
            caught.value.checkpoint,
            EXPERIMENTS,
            n=2,
        )
    with pytest.raises(WorkflowResumeMismatchError, match="idempotency"):
        client.workflows.resume_add_experiments_train_and_ask(
            caught.value.checkpoint,
            EXPERIMENTS,
            n=1,
            idempotency_key="different-workflow-key-0002",
        )

    assert len(scenario.calls) == calls_before
    client.close()
    http_client.close()


def test_semantically_identical_rows_have_one_restart_fingerprint() -> None:
    """Mapping insertion order must not alter workflow identity or subkeys."""
    scenario = WorkflowScenario(fail_at="batch")
    client, http_client = _client(scenario)
    reordered = [
        {
            "valid_outputs": {"yield": True},
            "outputs": {"yield": 73.0},
            "inputs": {"temperature": 80.0},
            "labcode": "run-001",
        }
    ]

    with pytest.raises(AddExperimentsTrainAndAskError) as first:
        _run(client)
    with pytest.raises(AddExperimentsTrainAndAskError) as second:
        client.workflows.add_experiments_train_and_ask(
            CAMPAIGN_ID,
            reordered,
            n=1,
            idempotency_key=IDEMPOTENCY_KEY,
        )

    assert first.value.checkpoint.request_fingerprint == (
        second.value.checkpoint.request_fingerprint
    )
    assert first.value.checkpoint.idempotency_keys == (
        second.value.checkpoint.idempotency_keys
    )
    client.close()
    http_client.close()


def test_sync_callback_failure_stops_before_training_and_resumes_after_upload() -> None:
    """Caller progress code must not retry or cancel completed remote work."""
    scenario = WorkflowScenario()
    client, http_client = _client(scenario)

    def callback(event: WorkflowProgressEvent) -> None:
        """Fail immediately after the durable batch completed.

        Args:
            event: Typed workflow progress event.

        Raises:
            RuntimeError: At the completed upload event.

        """
        if event.phase is WorkflowPhase.upload and event.status.value == "completed":
            raise RuntimeError("progress sink unavailable")

    with pytest.raises(WorkflowProgressCallbackError) as caught:
        _run(client, on_progress=callback)

    assert caught.value.checkpoint.stage is WorkflowStage.experiments_upserted
    assert scenario.count("batch") == 1
    assert scenario.count("train_submit") == 0
    result = client.workflows.resume_add_experiments_train_and_ask(
        caught.value.checkpoint,
        EXPERIMENTS,
        n=1,
        timeout=10,
        poll_interval=0.01,
    )
    assert result.checkpoint.stage is WorkflowStage.completed
    assert scenario.count("batch") == 1
    client.close()
    http_client.close()


def test_training_required_race_never_repeats_completed_training() -> None:
    """A stale-between-Train-and-Ask race must surface without hidden retraining."""
    scenario = WorkflowScenario(training_required_at_ask=True)
    client, http_client = _client(scenario)

    with pytest.raises(AddExperimentsTrainAndAskError) as first:
        _run(client)
    assert first.value.checkpoint.stage is WorkflowStage.training_completed
    assert isinstance(first.value.__cause__, TrainingRequiredError)

    with pytest.raises(AddExperimentsTrainAndAskError) as second:
        client.workflows.resume_add_experiments_train_and_ask(
            first.value.checkpoint,
            EXPERIMENTS,
            n=1,
        )

    assert second.value.checkpoint.stage is WorkflowStage.training_completed
    assert scenario.count("train_submit") == 1
    assert scenario.count("ask_submit") == 2
    client.close()
    http_client.close()


@pytest.mark.parametrize(
    ("n", "poll_interval", "expected_error"),
    [(0, 1.0, ValidationError), (1, 0.0, ConfigurationError)],
)
def test_sync_workflow_validates_all_local_input_before_upload(
    n: int,
    poll_interval: float,
    expected_error: type[Exception],
) -> None:
    """Invalid suggestion or waiting controls must perform zero HTTP calls.

    Args:
        n: Candidate count under test.
        poll_interval: Polling interval under test.
        expected_error: Exact local validation exception type.

    """
    scenario = WorkflowScenario()
    client, http_client = _client(scenario)

    with pytest.raises(expected_error):
        client.workflows.add_experiments_train_and_ask(
            CAMPAIGN_ID,
            EXPERIMENTS,
            n=n,
            poll_interval=poll_interval,
        )

    assert scenario.calls == []
    client.close()
    http_client.close()


def test_unserializable_workflow_rows_fail_before_any_http_request() -> None:
    """Opaque Python objects cannot enter a restart fingerprint or remote batch."""
    scenario = WorkflowScenario()
    client, http_client = _client(scenario)

    with pytest.raises(ConfigurationError, match="deterministic JSON"):
        client.workflows.add_experiments_train_and_ask(
            CAMPAIGN_ID,
            [{"inputs": {"temperature": object()}}],
            n=1,
        )

    assert scenario.calls == []
    client.close()
    http_client.close()

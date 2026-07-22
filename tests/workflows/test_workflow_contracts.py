"""Pure-data contract tests for explicit composite workflow recovery."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from parampilot import (
    AddExperimentsTrainAndAskCheckpoint,
    AddExperimentsTrainAndAskError,
    AddExperimentsTrainAndAskResult,
    WorkflowProgressCallbackError,
    WorkflowProgressEvent,
    WorkflowResumeMismatchError,
)
from parampilot.workflow_models import WorkflowIdempotencyKeys, WorkflowStage
from tests.support import CAMPAIGN_ID, TOKEN


def _keys() -> WorkflowIdempotencyKeys:
    """Build valid deterministic-looking workflow subkeys.

    Returns:
        Typed workflow idempotency key set.

    """
    digest = "a" * 64
    return WorkflowIdempotencyKeys(
        experiments=f"ppw1.experiments.{digest}",
        training=f"ppw1.training.{digest}",
        training_cancel=f"ppw1.training_cancel.{digest}",
        ask=f"ppw1.ask.{digest}",
        ask_cancel=f"ppw1.ask_cancel.{digest}",
    )


def test_initialized_checkpoint_is_strict_serializable_and_secret_free() -> None:
    """Recovery state must contain only validated public workflow data."""
    checkpoint = AddExperimentsTrainAndAskCheckpoint(
        campaign_id=CAMPAIGN_ID,
        request_fingerprint="b" * 64,
        experiment_count=1,
        requested_suggestions=5,
        stage=WorkflowStage.initialized,
        idempotency_keys=_keys(),
    )

    encoded = checkpoint.model_dump_json()
    reconstructed = AddExperimentsTrainAndAskCheckpoint.model_validate_json(encoded)

    assert reconstructed == checkpoint
    assert TOKEN not in encoded
    assert "client" not in encoded
    assert "base_url" not in encoded
    assert "http" not in encoded
    assert json.loads(encoded)["version"] == 1


def test_checkpoint_rejects_claimed_completion_without_required_recovery_data() -> None:
    """Callers cannot forge a later stage while omitting completed artifacts."""
    with pytest.raises(ValidationError, match="batch_result|training_job_id"):
        AddExperimentsTrainAndAskCheckpoint(
            campaign_id=CAMPAIGN_ID,
            request_fingerprint="b" * 64,
            experiment_count=1,
            requested_suggestions=5,
            stage=WorkflowStage.training_completed,
            idempotency_keys=_keys(),
        )


def test_public_workflow_types_are_exposed_from_the_stable_import_root() -> None:
    """Primary result, recovery, progress, and error types must be discoverable."""
    assert AddExperimentsTrainAndAskCheckpoint.__name__.endswith("Checkpoint")
    assert AddExperimentsTrainAndAskResult.__name__.endswith("Result")
    assert AddExperimentsTrainAndAskError.__name__.endswith("Error")
    assert WorkflowResumeMismatchError.__name__.endswith("Error")
    assert WorkflowProgressCallbackError.__name__.endswith("Error")
    assert WorkflowProgressEvent.__name__.endswith("Event")

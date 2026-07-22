"""Stable public payload fixtures shared by workflow behavior tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tests.support import CAMPAIGN_ID

INPUT_EXPERIMENT_ID = "a410ed1d-f3d7-42c8-af36-fc7bdc7f1511"
SUGGESTION_ID = "22f80abe-3df1-4b12-ae4d-61ea777123ba"
TRAIN_JOB_ID = "ec5bb6e4-ff68-4422-a16e-08499d3acaaf"
ASK_JOB_ID = "51f50ac3-a3f2-44b3-829c-415af75d47cc"
WORKFLOW_CAPABILITIES = [
    "experiments.batch-upsert",
    "jobs.explicit-training",
    "jobs.observations",
]

EXPERIMENTS = [
    {
        "labcode": "run-001",
        "inputs": {"temperature": 80.0},
        "outputs": {"yield": 73.0},
        "valid_outputs": {"yield": True},
    }
]


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """One externally observable fake API operation.

    Args:
        operation: Stable test operation label.
        method: HTTP request method.
        path: Public request path.
        idempotency_key: Caller workflow subkey, if present.
        body: Decoded JSON request body, if present.

    """

    operation: str
    method: str
    path: str
    idempotency_key: str | None
    body: Any


def experiment_payload(
    *,
    experiment_id: str,
    labcode: str,
    status: str,
    inputs: dict[str, object],
) -> dict[str, Any]:
    """Build a complete public experiment response.

    Args:
        experiment_id: Public experiment UUID.
        labcode: Human-facing campaign labcode.
        status: Pending, done, or invalid lifecycle state.
        inputs: Campaign-domain input values.

    Returns:
        JSON-compatible experiment response.

    """
    return {
        "id": experiment_id,
        "campaign_id": CAMPAIGN_ID,
        "status": status,
        "labcode": labcode,
        "inputs": inputs,
        "outputs": {"yield": 73.0} if status == "done" else {},
        "valid_outputs": {"yield": True} if status == "done" else {},
        "extra_fields": {},
        "performed_at": "2026-07-14T12:00:00Z" if status == "done" else None,
        "predictions": None,
        "desirability": {},
        "total_score": None,
        "proposed_by_strategy": (
            "AdditiveSoboStrategy" if status == "pending" else None
        ),
        "is_transfer": False,
        "transfer_source_campaign_id": None,
        "transfer_source_experiment_id": None,
        "created_at": "2026-07-14T12:00:00Z",
        "updated_at": "2026-07-14T12:00:00Z",
    }


def model_job_payload(*, kind: str, job_id: str) -> dict[str, Any]:
    """Build a queued public model-job response.

    Args:
        kind: Train or Ask discriminator.
        job_id: Public model-job UUID.

    Returns:
        JSON-compatible job response.

    """
    return {
        "id": job_id,
        "campaign_id": CAMPAIGN_ID,
        "depends_on_job_id": None,
        "kind": kind,
        "status": "queued",
        "result_available": False,
        "terminal_error": None,
        "created_at": "2026-07-14T12:00:00Z",
        "updated_at": "2026-07-14T12:00:00Z",
        "queued_at": "2026-07-14T12:00:00Z",
        "claimed_at": None,
    }


__all__ = [
    "ASK_JOB_ID",
    "EXPERIMENTS",
    "INPUT_EXPERIMENT_ID",
    "RecordedCall",
    "SUGGESTION_ID",
    "TRAIN_JOB_ID",
    "WORKFLOW_CAPABILITIES",
    "experiment_payload",
    "model_job_payload",
]

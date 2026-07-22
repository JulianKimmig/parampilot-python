"""Semantic fixtures for generated model-job request and result contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

CAMPAIGN_ID = "a519d355-3bf8-4544-a69a-c45ad09c39f1"
JOB_ID = "61bf9762-5252-4267-bec3-a5e009245acb"


def test_job_status_kind_and_prediction_uncertainty_are_closed_and_bounded() -> None:
    """Closed job enums and nonnegative prediction deviation must be enforced."""
    from parampilot.models import ModelJobResponse, PredictResult

    payload = {
        "id": JOB_ID,
        "campaign_id": CAMPAIGN_ID,
        "depends_on_job_id": None,
        "kind": "train",
        "status": "queued",
        "result_available": False,
        "terminal_error": None,
        "created_at": "2026-07-14T12:00:00Z",
        "updated_at": "2026-07-14T12:00:00Z",
        "queued_at": "2026-07-14T12:00:00Z",
        "claimed_at": None,
    }

    assert ModelJobResponse.model_validate(payload).kind.value == "train"
    with pytest.raises(ValidationError):
        ModelJobResponse.model_validate({**payload, "kind": "optimize"})
    with pytest.raises(ValidationError):
        PredictResult.model_validate(
            {
                "kind": "predict",
                "predictions": [{"yield": {"mean": 1.0, "std": -0.1}}],
            }
        )

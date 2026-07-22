"""Semantic fixtures for generated campaign and experiment API contracts."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

CAMPAIGN_ID = "a519d355-3bf8-4544-a69a-c45ad09c39f1"
EXPERIMENT_ID = "b8f4af71-2a1f-4018-873e-8a231fa48a20"


def _domain() -> dict[str, Any]:
    """Build a compact valid optimization domain.

    Returns:
        JSON-compatible domain payload.

    """
    return {
        "type": "Domain",
        "inputs": {
            "type": "Inputs",
            "features": [
                {
                    "type": "ContinuousInput",
                    "key": "temperature",
                    "bounds": [20.0, 100.0],
                    "unit": "degC",
                }
            ],
        },
        "outputs": {
            "type": "Outputs",
            "features": [
                {
                    "type": "ContinuousOutput",
                    "key": "yield",
                    "objective": {"type": "MaximizeObjective"},
                }
            ],
        },
        "constraints": {"type": "Constraints", "constraints": []},
    }


def test_configured_campaign_request_round_trips_only_caller_supplied_fields() -> None:
    """Atomic campaign configuration must retain every supplied contract field."""
    from parampilot.models import ConfiguredCampaignCreateRequest

    domain = _domain()
    payload = {
        "name": "Esterification",
        "domain": domain,
        "strategy": {"type": "RandomStrategy", "domain": domain, "seed": 42},
        "additional_fields": {
            "fields": [{"type": "number", "name": "relative_waste", "required": True}]
        },
        "effects": [{"expression": "relative_waste = 100 * waste_mass / total_mass"}],
    }

    request = ConfiguredCampaignCreateRequest.model_validate(payload)

    assert request.model_dump(mode="json", by_alias=True, exclude_unset=True) == payload
    assert request.default_labcode == "ex"


def test_experiment_response_preserves_additive_fields_and_typed_identifiers() -> None:
    """Experiment responses must retain UUID/datetime types and additive server data."""
    from parampilot.models import ExperimentResponse

    response = ExperimentResponse.model_validate(
        {
            "id": EXPERIMENT_ID,
            "campaign_id": CAMPAIGN_ID,
            "status": "done",
            "labcode": "ex-001",
            "inputs": {"temperature": 80.0},
            "outputs": {"yield": 91.5},
            "valid_outputs": {"yield": True},
            "desirability": {"yield": 0.915},
            "total_score": 0.915,
            "predictions": None,
            "extra_fields": {"operator": "Ada"},
            "proposed_by_strategy": "RandomStrategy",
            "created_at": "2026-07-14T12:00:00Z",
            "updated_at": "2026-07-14T12:05:00Z",
            "future_server_field": "retained",
        }
    )

    assert str(response.id) == EXPERIMENT_ID
    assert response.created_at.utcoffset() is not None
    assert response.model_extra == {"future_server_field": "retained"}


def test_batch_and_prediction_request_bounds_reject_empty_or_oversized_payloads() -> (
    None
):
    """Bounded batch contracts must enforce both minimum and maximum row counts."""
    from parampilot.models import ExperimentBatchUpsertRequest, PredictionJobRequest

    with pytest.raises(ValidationError):
        ExperimentBatchUpsertRequest.model_validate({"items": []})
    with pytest.raises(ValidationError):
        ExperimentBatchUpsertRequest.model_validate(
            {"items": [{"labcode": f"ex-{index}"} for index in range(501)]}
        )
    with pytest.raises(ValidationError):
        PredictionJobRequest.model_validate({"rows": []})
    with pytest.raises(ValidationError):
        PredictionJobRequest.model_validate(
            {"rows": [{"temperature": 80.0} for _ in range(501)]}
        )


def test_experiment_patch_rejects_unknown_request_fields() -> None:
    """Partial request models must forbid fields outside the public contract."""
    from parampilot.models import ExperimentPatchRequest

    patch = ExperimentPatchRequest.model_validate(
        {"outputs": {"yield": 90.0}, "valid_outputs": {"yield": True}}
    )
    assert patch.model_dump(mode="json", exclude_unset=True) == {
        "outputs": {"yield": 90.0},
        "valid_outputs": {"yield": True},
    }
    with pytest.raises(ValidationError):
        ExperimentPatchRequest.model_validate({"private_database_id": 7})

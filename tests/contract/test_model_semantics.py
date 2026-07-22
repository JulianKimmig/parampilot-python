"""Semantic valid/invalid fixtures for critical generated Pydantic contracts."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

EXPERIMENT_ID = "b8f4af71-2a1f-4018-873e-8a231fa48a20"


def _domain_payload() -> dict[str, Any]:
    """Build a discriminated constrained domain fixture.

    Returns:
        JSON-compatible BoFire domain payload.

    """
    return {
        "type": "Domain",
        "inputs": {
            "type": "Inputs",
            "features": [
                {
                    "type": "ContinuousInput",
                    "key": "catalyst_a",
                    "bounds": [0.0, 1.0],
                    "unit": "mass %",
                },
                {
                    "type": "ContinuousInput",
                    "key": "catalyst_b",
                    "bounds": [0.0, 3.0],
                    "unit": "mass %",
                },
            ],
        },
        "outputs": {
            "type": "Outputs",
            "features": [
                {
                    "type": "ContinuousOutput",
                    "key": "yield",
                    "objective": {
                        "type": "MaximizeObjective",
                        "bounds": [0.0, 100.0],
                    },
                }
            ],
        },
        "constraints": {
            "type": "Constraints",
            "constraints": [
                {
                    "type": "NChooseKConstraint",
                    "features": ["catalyst_a", "catalyst_b"],
                    "min_count": 1,
                    "max_count": 1,
                    "none_also_valid": True,
                }
            ],
        },
    }


def _stepwise_payload() -> dict[str, Any]:
    """Build a two-stage random-to-SOBO strategy fixture.

    Returns:
        JSON-compatible discriminated Stepwise strategy.

    """
    domain = _domain_payload()
    return {
        "type": "StepwiseStrategy",
        "domain": domain,
        "seed": 42,
        "steps": [
            {
                "type": "Step",
                "condition": {
                    "type": "NumberOfExperimentsCondition",
                    "n_experiments": 5,
                },
                "strategy_data": {
                    "type": "RandomStrategy",
                    "domain": domain,
                    "seed": 42,
                },
            },
            {
                "type": "Step",
                "condition": {"type": "AlwaysTrueCondition"},
                "strategy_data": {
                    "type": "AdditiveSoboStrategy",
                    "domain": domain,
                    "seed": 42,
                },
            },
        ],
    }


def test_public_model_facade_exports_all_representative_contract_families() -> None:
    """Stable imports must expose domain, API, error, and job contract types."""
    from parampilot.models import (
        AskResult,
        ConfiguredCampaignCreateRequest,
        Domain,
        PublicApiErrorResponse,
        StepwiseStrategy,
        TrainResult,
    )

    assert Domain.__name__ == "Domain"
    assert StepwiseStrategy.__name__ == "StepwiseStrategy"
    assert ConfiguredCampaignCreateRequest.__name__ == (
        "ConfiguredCampaignCreateRequest"
    )
    assert PublicApiErrorResponse.__name__ == "PublicApiErrorResponse"
    assert TrainResult.__name__ == "TrainResult"
    assert AskResult.__name__ == "AskResult"


def test_domain_and_strategy_discriminators_round_trip_wire_payloads() -> None:
    """Critical BoFire unions must select concrete types and retain wire aliases."""
    from parampilot.models import (
        AdditiveSoboStrategy,
        ContinuousInput,
        Domain,
        RandomStrategy,
        StepwiseStrategy,
    )

    domain = Domain.model_validate(_domain_payload())
    strategy = StepwiseStrategy.model_validate(_stepwise_payload())

    assert isinstance(domain.inputs.features[0], ContinuousInput)
    assert isinstance(strategy.steps[0].strategy_data, RandomStrategy)
    assert isinstance(strategy.steps[1].strategy_data, AdditiveSoboStrategy)
    assert domain.model_dump(mode="json", by_alias=True, exclude_unset=True) == (
        _domain_payload()
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"type": "MysteryInput", "key": "x", "bounds": [0, 1]},
        {"type": "ContinuousInput", "key": "x", "bounds": [0]},
        {"type": "ContinuousInput", "key": "x", "bounds": [0, 1], "extra": 1},
    ],
)
def test_invalid_domain_union_constraint_and_unknown_field_are_rejected(
    mutation: dict[str, Any],
) -> None:
    """Request contracts must reject ambiguous or structurally invalid inputs.

    Args:
        mutation: Invalid replacement for the first domain input.

    """
    from parampilot.models import Domain

    payload = _domain_payload()
    payload["inputs"]["features"][0] = mutation

    with pytest.raises(ValidationError):
        Domain.model_validate(payload)


def test_additional_fields_effects_and_job_request_bounds_are_enforced() -> None:
    """ParamPilot request-only constraints must remain concrete and strict."""
    from parampilot.models import (
        AskJobRequest,
        CampaignEffectRequest,
        ExtraData,
    )

    additional_fields = ExtraData.model_validate(
        {"fields": [{"type": "number", "name": "relative_waste"}]}
    )
    effect = CampaignEffectRequest.model_validate(
        {"expression": "relative_waste = 100 * waste_mass / total_mass"}
    )

    assert additional_fields.fields[0].name == "relative_waste"
    assert effect.expression.startswith("relative_waste")
    with pytest.raises(ValidationError):
        ExtraData.model_validate({"fields": [{"type": "number", "name": "bad name"}]})
    with pytest.raises(ValidationError):
        CampaignEffectRequest.model_validate({"expression": ""})
    with pytest.raises(ValidationError):
        AskJobRequest.model_validate({"n": 501})


def test_canonical_error_and_page_models_validate_typed_fields() -> None:
    """Errors and cursor pages must retain issue paths and aware timestamps."""
    from parampilot.models import CampaignPageResponse, PublicApiErrorResponse

    error = PublicApiErrorResponse.model_validate(
        {
            "error": {
                "code": "validation_error",
                "message": "Invalid request.",
                "request_id": "req_opaque",
                "retryable": False,
                "issues": [
                    {"code": "invalid", "message": "Bad value.", "path": ["rows", 0]}
                ],
            }
        }
    )
    page = CampaignPageResponse.model_validate(
        {
            "items": [],
            "next_cursor": None,
            "has_more": False,
            "snapshot_at": "2026-07-14T12:00:00Z",
            "future_page_field": True,
        }
    )

    dumped_error = error.model_dump(mode="json", by_alias=True)
    assert dumped_error["error"]["issues"][0]["path"] == ["rows", 0]
    assert page.snapshot_at.utcoffset() is not None
    assert page.model_extra == {"future_page_field": True}
    with pytest.raises(ValidationError):
        PublicApiErrorResponse.model_validate(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request.",
                    "request_id": "req_opaque",
                    "retryable": False,
                    "issues": [
                        {"code": "invalid", "message": "Bad.", "path": ["rows", -1]}
                    ],
                }
            }
        )


def test_all_three_terminal_job_results_are_concrete_discriminated_models() -> None:
    """Train, Ask, and Predict results must never collapse to generic dictionaries."""
    from parampilot.models import AskResult, PredictResult, TrainResult

    adapter = TypeAdapter(TrainResult | AskResult | PredictResult)
    results = [
        adapter.validate_python(
            {
                "kind": "train",
                "model_revision": "rev-7",
                "artifact_ready": True,
                "grid_predictions_ready": False,
                "shap_results_ready": True,
            }
        ),
        adapter.validate_python(
            {"kind": "ask", "created_experiment_ids": [EXPERIMENT_ID]}
        ),
        adapter.validate_python(
            {
                "kind": "predict",
                "predictions": [{"yield": {"mean": 80.0, "std": 1.5}}],
            }
        ),
    ]

    assert isinstance(results[0], TrainResult)
    assert isinstance(results[1], AskResult)
    assert isinstance(results[2], PredictResult)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "unknown"})

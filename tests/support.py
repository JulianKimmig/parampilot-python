"""Shared wire fixtures for SDK transport and resource behavior tests."""

from __future__ import annotations

from typing import Any

from parampilot.models import Domain, RandomStrategy

CAMPAIGN_ID = "a519d355-3bf8-4544-a69a-c45ad09c39f1"
EXPERIMENT_ID = "b8f4af71-2a1f-4018-873e-8a231fa48a20"
JOB_ID = "61bf9762-5252-4267-bec3-a5e009245acb"
TOKEN = "pp_test_secret_token"
SCHEMA_DIGEST = (
    "sha256:a657824fc73aac598a530652348f441b7c3c3f37641d1d6972617487b8b6b1db"
)


def domain_and_strategy() -> tuple[Domain, RandomStrategy]:
    """Build minimal valid optimization contracts for operation invocations.

    Returns:
        Typed domain and matching random strategy.

    """
    domain = Domain.model_validate(
        {
            "type": "Domain",
            "inputs": {
                "type": "Inputs",
                "features": [
                    {
                        "type": "ContinuousInput",
                        "key": "temperature",
                        "bounds": [20.0, 100.0],
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
    )
    strategy = RandomStrategy.model_validate(
        {"type": "RandomStrategy", "domain": domain, "seed": 42}
    )
    return domain, strategy


def availability_payload(
    *,
    api_version: str = "2.0.0",
    capabilities: list[str] | None = None,
    schema_digest: str | None = None,
) -> dict[str, Any]:
    """Build a representative availability response.

    Args:
        api_version: Server API semantic version.
        capabilities: Open capability names to return.
        schema_digest: Optional exact digest override.

    Returns:
        JSON-compatible availability payload.

    """
    return {
        "status": "ok",
        "api_version": api_version,
        "capabilities": capabilities or [],
        "schema_digest": schema_digest or SCHEMA_DIGEST,
        "token_expires_at": None,
        "user": {
            "id": "1c4704e7-8261-49a0-a0ef-74dd23fd9165",
            "username": "sdk-user",
            "preferred_language": "en",
        },
    }


def campaign_payload(*, name: str = "Esterification") -> dict[str, Any]:
    """Build a complete campaign response payload.

    Args:
        name: Campaign name.

    Returns:
        JSON-compatible campaign response.

    """
    return {
        "id": CAMPAIGN_ID,
        "name": name,
        "description": "",
        "started": False,
        "default_labcode": "ex",
        "access_level": "owner",
        "settings": {},
        "domain": None,
        "strategy": None,
        "additional_fields": {"fields": []},
        "effects": [],
        "transfer_links": [],
        "created_at": "2026-07-14T12:00:00Z",
        "updated_at": "2026-07-14T12:00:00Z",
    }


def campaign_summary_payload(*, name: str) -> dict[str, Any]:
    """Build one campaign collection item.

    Args:
        name: Campaign name.

    Returns:
        JSON-compatible campaign summary.

    """
    return {
        "id": CAMPAIGN_ID,
        "name": name,
        "description": "",
        "started": False,
        "default_labcode": "ex",
        "access_level": "owner",
        "created_at": "2026-07-14T12:00:00Z",
        "updated_at": "2026-07-14T12:00:00Z",
        "experiment_count": 0,
        "objective_count": 0,
        "latest_model_job_kind": None,
        "latest_model_job_status": None,
        "is_default": False,
    }


def model_job_payload(*, kind: str = "ask") -> dict[str, Any]:
    """Build one queued model-job response.

    Args:
        kind: Public job discriminator.

    Returns:
        JSON-compatible job response.

    """
    return {
        "id": JOB_ID,
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


def job_observation_payload(
    *,
    status: str,
    kind: str = "train",
    stage: str = "fitting_model",
) -> dict[str, Any]:
    """Build one lean validated model-job observation.

    Args:
        status: Public job lifecycle state.
        kind: Train, Ask, or Predict discriminator.
        stage: Canonical progress stage for running observations.

    Returns:
        JSON-compatible public observation payload.

    """
    terminal_error = None
    if status == "failed":
        terminal_error = {
            "code": "job_failed",
            "message": "The model job failed safely.",
            "context": None,
        }
    elif status == "canceled":
        terminal_error = {
            "code": "job_canceled",
            "message": "The model job was canceled.",
            "context": None,
        }
    return {
        "id": JOB_ID,
        "campaign_id": CAMPAIGN_ID,
        "depends_on_job_id": None,
        "kind": kind,
        "status": status,
        "progress": (
            {
                "contract_version": 1,
                "stage": stage,
                "changed_at": "2026-07-14T12:00:01Z",
                "detail": {"completed": 1, "total": 2, "unit": "rows"},
            }
            if status == "running"
            else None
        ),
        "liveness": {
            "state": "active" if status == "running" else "not_applicable",
            "checked_at": "2026-07-14T12:00:02Z",
            "last_contact_at": (
                "2026-07-14T12:00:01Z" if status == "running" else None
            ),
        },
        "terminal_error": terminal_error,
        "available_actions": {
            "can_cancel": status in {"planned", "queued", "running"},
            "can_queue": status == "planned",
        },
    }


def job_result_payload(*, kind: str = "train") -> dict[str, Any]:
    """Build one concrete terminal model-job result payload.

    Args:
        kind: Train, Ask, or Predict result discriminator.

    Returns:
        JSON-compatible terminal result.

    Raises:
        AssertionError: If ``kind`` is outside the public result union.

    """
    if kind == "train":
        return {
            "kind": "train",
            "model_revision": "model-v1",
            "artifact_ready": True,
            "grid_predictions_ready": True,
            "shap_results_ready": True,
        }
    if kind == "ask":
        return {"kind": "ask", "created_experiment_ids": [EXPERIMENT_ID]}
    if kind == "predict":
        return {
            "kind": "predict",
            "predictions": [{"yield": {"mean": 90.0, "std": 1.0}}],
        }
    raise AssertionError(f"Unsupported job result kind {kind!r}")


def canonical_error(
    code: str,
    *,
    retryable: bool = False,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical API error envelope.

    Args:
        code: Stable server error code.
        retryable: Server retry classification.
        context: Optional privacy-safe structured context.

    Returns:
        JSON-compatible canonical error response.

    """
    return {
        "error": {
            "code": code,
            "message": f"Server reported {code}.",
            "request_id": "req-safe-123",
            "retryable": retryable,
            "issues": [],
            "context": context,
        }
    }

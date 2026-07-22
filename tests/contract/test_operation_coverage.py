"""Contract tests for generated operation metadata and reviewed SDK coverage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PACKAGE_ROOT / "contracts" / "programmatic-openapi.json"
OPERATIONS_PATH = PACKAGE_ROOT / "src" / "parampilot" / "generated" / "operations.json"
COVERAGE_PATH = PACKAGE_ROOT / "contracts" / "operation-coverage.json"
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}


def _load_json(path: Path) -> dict[str, Any]:
    """Load a top-level JSON object.

    Args:
        path: JSON file to decode.

    Returns:
        Decoded JSON object.

    """
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    return value


def _schema_operations(schema: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Map every OpenAPI operation ID to its method and path.

    Args:
        schema: Decoded OpenAPI document.

    Returns:
        Operation ID to uppercase method/path pair.

    """
    operations: dict[str, tuple[str, str]] = {}
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                operations[operation["operationId"]] = (method.upper(), path)
    return operations


def test_metadata_and_coverage_exactly_match_all_openapi_operations() -> None:
    """No backend, generated, or reviewed SDK operation may be missing or orphaned."""
    schema_operations = _schema_operations(_load_json(SCHEMA_PATH))
    metadata = _load_json(OPERATIONS_PATH)
    coverage = _load_json(COVERAGE_PATH)
    generated_operations = {
        item["operation_id"]: (item["method"], item["path"])
        for item in metadata["operations"]
    }

    assert metadata["format_version"] == 1
    assert coverage["format_version"] == 1
    assert len(schema_operations) == 39
    assert generated_operations == schema_operations
    assert set(coverage["operations"]) == set(schema_operations)
    assert coverage["exclusions"] == []


def test_every_coverage_entry_names_an_honest_client_destination() -> None:
    """Coverage must name the task that implemented every async destination."""
    coverage = _load_json(COVERAGE_PATH)

    for operation_id, entry in coverage["operations"].items():
        assert entry["resource"]
        assert entry["method"]
        assert entry["status"] == "implemented"
        expected_task = "TASK-007" if operation_id == "getAvailability" else "TASK-009"
        assert entry["task"] == expected_task
        assert isinstance(entry["may_train"], bool)
        assert operation_id

    assert coverage["operations"]["getAvailability"] == {
        "may_train": False,
        "method": "get_availability",
        "resource": "client",
        "status": "implemented",
        "task": "TASK-007",
    }


def test_only_explicit_training_operation_can_be_marked_as_training() -> None:
    """Generated coverage must preserve the no-hidden-training call boundary."""
    coverage = _load_json(COVERAGE_PATH)
    training_entries = {
        operation_id: entry
        for operation_id, entry in coverage["operations"].items()
        if entry["may_train"]
    }

    assert set(training_entries) == {"createTrainingJob"}
    assert "train" in training_entries["createTrainingJob"]["method"]


def test_operation_metadata_preserves_auth_media_and_concurrency_contracts() -> None:
    """Representative generated operations must retain critical wire behavior."""
    metadata = _load_json(OPERATIONS_PATH)
    operations = {item["operation_id"]: item for item in metadata["operations"]}

    availability = operations["getAvailability"]
    assert availability["auth"] == {
        "required": True,
        "schemes": ["ProgrammaticApiTokenAuth"],
    }
    assert availability["idempotency"] == {
        "classification": "safe_read",
        "key_required": False,
        "precondition_required": False,
        "revalidation_supported": False,
    }
    assert (
        availability["responses"]["200"]["content"]["application/json"]["schema_name"]
        == "AvailabilityResponse"
    )

    create = operations["createCampaign"]
    assert create["request_body"]["content"]["application/json"]["schema_name"] == (
        "CampaignCreateRequest"
    )
    assert create["idempotency"]["classification"] == "keyed_mutation"
    assert create["idempotency"]["key_required"] is True

    replace = operations["replaceCampaignDomain"]
    assert replace["idempotency"]["precondition_required"] is True

    download = operations["downloadGridPredictions"]
    assert download["idempotency"]["revalidation_supported"] is True
    assert set(download["responses"]["200"]["content"]) == {
        "application/json",
        "application/vnd.apache.arrow.stream",
    }

    query = operations["queryEffectiveExperiments"]
    assert query["method"] == "POST"
    assert query["idempotency"]["classification"] == "manual_retry"


def test_operation_metadata_rendering_is_deterministic() -> None:
    """Identical schema input must produce byte-identical operation metadata."""
    from parampilot_codegen.artifacts import render_json
    from parampilot_codegen.operations import build_operations_document

    schema = _load_json(SCHEMA_PATH)

    first = render_json(build_operations_document(schema))
    second = render_json(build_operations_document(schema))

    assert first == second

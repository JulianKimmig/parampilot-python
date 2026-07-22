"""Validation for the reviewed OpenAPI-to-client operation coverage manifest."""

from __future__ import annotations

from typing import Any


def _operation_ids(operations: dict[str, Any]) -> set[str]:
    """Extract generated operation IDs.

    Args:
        operations: Generated operations document.

    Returns:
        Operation ID set.

    Raises:
        ValueError: If the generated operation structure is invalid.

    """
    values = operations.get("operations")
    if not isinstance(values, list):
        raise ValueError("Generated operations must contain an operations array")
    identifiers: set[str] = set()
    for value in values:
        if not isinstance(value, dict) or not isinstance(
            value.get("operation_id"), str
        ):
            raise ValueError("Every generated operation must have an operation_id")
        identifiers.add(value["operation_id"])
    if len(identifiers) != len(values):
        raise ValueError("Generated operation IDs must be unique")
    return identifiers


def validate_coverage(
    coverage: dict[str, Any],
    operations: dict[str, Any],
) -> None:
    """Require exact, honest, and training-safe operation coverage.

    Args:
        coverage: Reviewed client coverage manifest.
        operations: Generated operation metadata document.

    Raises:
        ValueError: If coverage is missing, orphaned, malformed, or unsafe.

    """
    if coverage.get("format_version") != 1:
        raise ValueError("Coverage format_version must be 1")
    exclusions = coverage.get("exclusions")
    if not isinstance(exclusions, list):
        raise ValueError("Coverage exclusions must be an array")
    entries = coverage.get("operations")
    if not isinstance(entries, dict):
        raise ValueError("Coverage operations must be an object")
    expected = _operation_ids(operations)
    actual = set(entries)
    if expected != actual:
        missing = sorted(expected - actual)
        orphaned = sorted(actual - expected)
        raise ValueError(f"Coverage drift: missing={missing}, orphaned={orphaned}")

    training_operations: set[str] = set()
    for operation_id in sorted(entries):
        entry = entries[operation_id]
        if not isinstance(entry, dict):
            raise ValueError(f"Coverage entry {operation_id} must be an object")
        required = {"may_train", "method", "resource", "status", "task"}
        if set(entry) != required:
            raise ValueError(
                f"Coverage entry {operation_id} must contain {sorted(required)}"
            )
        if entry["status"] not in {"implemented", "planned"}:
            raise ValueError(f"Coverage entry {operation_id} has invalid status")
        if not isinstance(entry["method"], str) or not entry["method"]:
            raise ValueError(f"Coverage entry {operation_id} needs a method")
        if not isinstance(entry["resource"], str) or not entry["resource"]:
            raise ValueError(f"Coverage entry {operation_id} needs a resource")
        if not isinstance(entry["may_train"], bool):
            raise ValueError(f"Coverage entry {operation_id} needs boolean may_train")
        if entry["may_train"]:
            training_operations.add(operation_id)
            if "train" not in entry["method"]:
                raise ValueError(f"Training method {operation_id} must be train-named")
    if training_operations != {"createTrainingJob"}:
        raise ValueError(
            "Only createTrainingJob may be marked as training-capable; "
            f"found {sorted(training_operations)}"
        )

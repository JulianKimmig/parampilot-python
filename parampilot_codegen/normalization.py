"""Lossless OpenAPI normalization for qualified generator edge cases."""

from __future__ import annotations

from typing import Any

UNION_CONSTRAINT_KEYS = frozenset(
    {
        "exclusiveMaximum",
        "exclusiveMinimum",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "pattern",
        "uniqueItems",
    }
)


def _normalize(value: Any) -> Any:
    """Recursively copy and normalize one decoded JSON value.

    Args:
        value: Decoded JSON value.

    Returns:
        Independent normalized value.

    Raises:
        ValueError: If overlapping branch and union constraints conflict.

    """
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {key: _normalize(item) for key, item in value.items()}
    union_keys = [key for key in ("anyOf", "oneOf") if key in normalized]
    constraints = {
        key: normalized[key] for key in UNION_CONSTRAINT_KEYS if key in normalized
    }
    if not union_keys or not constraints:
        return normalized
    if len(union_keys) != 1:
        raise ValueError("A schema node cannot normalize both anyOf and oneOf")
    union_key = union_keys[0]
    branches = normalized[union_key]
    if not isinstance(branches, list):
        raise ValueError(f"{union_key} must be an array")

    for branch in branches:
        if not isinstance(branch, dict):
            raise ValueError(f"{union_key} branches must be objects")
        if branch.get("type") == "null":
            continue
        for key, constraint in constraints.items():
            if key in branch and branch[key] != constraint:
                raise ValueError(
                    f"Cannot normalize conflicting {key}: "
                    f"branch={branch[key]!r}, union={constraint!r}"
                )
            branch[key] = constraint
    for key in constraints:
        del normalized[key]
    return normalized


def normalize_schema_for_codegen(schema: dict[str, Any]) -> dict[str, Any]:
    """Move union-level constraints onto non-null branches for code generation.

    ``datamodel-code-generator`` otherwise duplicates these constraints on an
    outer generated ``RootModel`` field. Pydantic then applies length or
    numeric constraints to the wrapper object instead of its wire value. This
    adapter preserves the JSON Schema intersection while removing that
    generator-only duplication and never mutates the committed input.

    Args:
        schema: Complete exact public OpenAPI document.

    Returns:
        Independent schema object suitable for model generation.

    """
    normalized = _normalize(schema)
    if not isinstance(normalized, dict):
        raise ValueError("Normalized OpenAPI document must remain an object")
    return normalized

"""Sanitized provenance manifest construction for generated SDK contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from parampilot_codegen.artifacts import file_metadata, sha256_bytes
from parampilot_codegen.configuration import (
    CANONICAL_SCHEMA,
    COVERAGE_MANIFEST,
    GENERATOR_DISTRIBUTION,
    GENERATOR_PRESET,
    GENERATOR_VERSION,
    HASHED_OUTPUTS,
    PACKAGE_ROOT,
    TARGET_PYDANTIC,
    TARGET_PYTHON,
)


def _schema_count(schema: dict[str, Any]) -> int:
    """Return the number of named component schemas.

    Args:
        schema: Complete OpenAPI document.

    Returns:
        Named schema count.

    Raises:
        ValueError: If the required component structure is absent.

    """
    components = schema.get("components")
    if not isinstance(components, dict):
        raise ValueError("OpenAPI components must be an object")
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        raise ValueError("OpenAPI components.schemas must be an object")
    return len(schemas)


def _path_count(schema: dict[str, Any]) -> int:
    """Return the number of declared OpenAPI paths.

    Args:
        schema: Complete OpenAPI document.

    Returns:
        Path count.

    Raises:
        ValueError: If the required paths structure is absent.

    """
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI paths must be an object")
    return len(paths)


def build_provenance(
    schema: dict[str, Any],
    operation_count: int,
    generated_root: Path,
    normalized_schema: bytes,
) -> dict[str, Any]:
    """Build a deterministic path-sanitized generation manifest.

    Args:
        schema: Complete canonical OpenAPI document.
        operation_count: Number of generated stable operations.
        generated_root: Temporary artifact root.
        normalized_schema: Exact generator-adapted input bytes.

    Returns:
        JSON-compatible provenance object.

    """
    schema_metadata = file_metadata(generated_root, CANONICAL_SCHEMA)
    schema_metadata.update(
        {
            "openapi": schema["openapi"],
            "operations": operation_count,
            "paths": _path_count(schema),
            "schemas": _schema_count(schema),
            "normalized_bytes": len(normalized_schema),
            "normalized_sha256": sha256_bytes(normalized_schema),
        }
    )
    outputs = {
        path.as_posix(): file_metadata(generated_root, path) for path in HASHED_OUTPUTS
    }
    return {
        "format_version": 1,
        "generator": {
            "distribution": GENERATOR_DISTRIBUTION,
            "options": {
                "formatters": ["builtin"],
                "openapi_scopes": ["schemas"],
                "remote_refs": False,
                "root_model_sequence_interface": True,
                "schema_adapter": "union-constraints-v1",
                "schema_version": "3.1",
                "schema_version_mode": "strict",
            },
            "preset": GENERATOR_PRESET,
            "target_pydantic": TARGET_PYDANTIC,
            "target_python": TARGET_PYTHON,
            "version": GENERATOR_VERSION,
        },
        "input": schema_metadata,
        "outputs": outputs,
        "reviewed_inputs": {
            "operation_coverage": file_metadata(PACKAGE_ROOT, COVERAGE_MANIFEST)
        },
    }

"""Stable paths and generator options for public contract generation."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SCHEMA = Path("contracts/programmatic-openapi.json")
COVERAGE_MANIFEST = Path("contracts/operation-coverage.json")
MODELS_OUTPUT = Path("src/parampilot/generated/models.py")
MODEL_EXPORTS_OUTPUT = Path("src/parampilot/generated/model_exports.py")
OPERATIONS_OUTPUT = Path("src/parampilot/generated/operations.json")
PROVENANCE_OUTPUT = Path("src/parampilot/generated/provenance.json")
MODEL_STUB_OUTPUT = Path("src/parampilot/models/__init__.pyi")
GENERATED_OUTPUTS = (
    MODELS_OUTPUT,
    MODEL_EXPORTS_OUTPUT,
    OPERATIONS_OUTPUT,
    PROVENANCE_OUTPUT,
    MODEL_STUB_OUTPUT,
)
HASHED_OUTPUTS = (
    MODELS_OUTPUT,
    MODEL_EXPORTS_OUTPUT,
    OPERATIONS_OUTPUT,
    MODEL_STUB_OUTPUT,
)
GENERATOR_DISTRIBUTION = "datamodel-code-generator"
GENERATOR_VERSION = "0.68.1"
GENERATOR_PRESET = "practical-py310-20260619"
TARGET_PYTHON = "3.10"
TARGET_PYDANTIC = "2.12"


def model_generator_command(schema_path: Path, output_path: Path) -> list[str]:
    """Build the fully pinned datamodel-code-generator invocation.

    Args:
        schema_path: Canonical OpenAPI input path.
        output_path: Temporary destination for generated Pydantic source.

    Returns:
        Subprocess argument vector without shell interpretation.

    """
    return [
        sys.executable,
        "-m",
        "datamodel_code_generator",
        "--input",
        str(schema_path),
        "--input-file-type",
        "openapi",
        "--schema-version",
        "3.1",
        "--schema-version-mode",
        "strict",
        "--no-allow-remote-refs",
        "--preset",
        GENERATOR_PRESET,
        "--output-model-type",
        "pydantic_v2.BaseModel",
        "--target-pydantic-version",
        TARGET_PYDANTIC,
        "--openapi-scopes",
        "schemas",
        "--formatters",
        "builtin",
        "--disable-timestamp",
        "--enable-generated-header-marker",
        "--use-root-model-sequence-interface",
        "--output",
        str(output_path),
        "--ignore-pyproject",
    ]

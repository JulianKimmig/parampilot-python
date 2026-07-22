"""Deterministic public extraction manifest construction and parsing."""

from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from parampilot_release.configuration import (
    ALLOWLIST_VERSION,
    PUBLIC_SOURCE_ALLOWLIST,
    load_public_source_allowlist,
)
from parampilot_release.errors import PublicAuditError
from parampilot_release.hashing import sha256_file

SCHEMA_PATH = PurePosixPath("contracts/programmatic-openapi.json")
PROVENANCE_PATH = PurePosixPath("src/parampilot/generated/provenance.json")


def build_manifest(
    public_root: Path,
    relative_paths: tuple[PurePosixPath, ...],
    source_commit: str,
) -> dict[str, Any]:
    """Build a deterministic review manifest for exact extracted bytes.

    Args:
        public_root: Temporary extracted public tree.
        relative_paths: Sorted allowlisted file paths.
        source_commit: Exact private source commit.

    Returns:
        JSON-compatible manifest object.

    """
    provenance = _json_object(public_root, PROVENANCE_PATH)
    schema = _json_object(public_root, SCHEMA_PATH)
    load_public_source_allowlist(public_root)
    try:
        pyproject = tomllib.loads(
            (public_root / "pyproject.toml").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PublicAuditError("public project metadata is invalid") from error
    project = _object(pyproject.get("project"), "project metadata")
    distribution = _string(project.get("name"), "project distribution")
    package_version = _string(project.get("version"), "project version")
    input_metadata = _object(provenance.get("input"), "generator input")
    schema_path = public_root.joinpath(*SCHEMA_PATH.parts)
    schema_digest = sha256_file(schema_path)
    if input_metadata.get("sha256") != schema_digest:
        raise PublicAuditError("generator provenance does not match the public schema")
    components = _object(schema.get("components"), "OpenAPI components")
    schemas = _object(components.get("schemas"), "OpenAPI component schemas")
    paths = _object(schema.get("paths"), "OpenAPI paths")
    operations = sum(
        1
        for path_item in paths.values()
        if isinstance(path_item, dict)
        for method in path_item
        if method.lower()
        in {"delete", "get", "head", "options", "patch", "post", "put"}
    )
    files = [
        {
            "bytes": public_root.joinpath(*path.parts).stat().st_size,
            "path": path.as_posix(),
            "sha256": sha256_file(public_root.joinpath(*path.parts)),
        }
        for path in relative_paths
    ]
    generator = _object(provenance.get("generator"), "generator")
    generator_distribution = _string(
        generator.get("distribution"),
        "generator distribution",
    )
    generator_version = _string(generator.get("version"), "generator version")
    return {
        "allowlist_version": ALLOWLIST_VERSION,
        "allowlist": {
            "path": PUBLIC_SOURCE_ALLOWLIST.as_posix(),
            "sha256": sha256_file(public_root.joinpath(*PUBLIC_SOURCE_ALLOWLIST.parts)),
        },
        "files": files,
        "format_version": 1,
        "generator": {
            "distribution": generator_distribution,
            "path": PROVENANCE_PATH.as_posix(),
            "sha256": sha256_file(public_root.joinpath(*PROVENANCE_PATH.parts)),
            "version": generator_version,
        },
        "package": {
            "distribution": distribution,
            "version": package_version,
        },
        "schema": {
            "bytes": schema_path.stat().st_size,
            "operations": operations,
            "path": SCHEMA_PATH.as_posix(),
            "paths": len(paths),
            "schemas": len(schemas),
            "sha256": schema_digest,
        },
        "source_commit": source_commit,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    """Load one manifest as a strict top-level JSON object.

    Args:
        path: Manifest path.

    Returns:
        Decoded manifest object.

    Raises:
        PublicAuditError: If the manifest is absent, invalid, or not an object.

    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicAuditError(
            "public extraction manifest is missing or invalid"
        ) from error
    return _object(value, "manifest")


def _json_object(root: Path, path: PurePosixPath) -> dict[str, Any]:
    """Load one required relative JSON object.

    Args:
        root: Public tree root.
        path: Relative JSON path.

    Returns:
        Decoded JSON object.

    """
    try:
        value = json.loads(root.joinpath(*path.parts).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicAuditError(f"public JSON is missing or invalid: {path}") from error
    return _object(value, path.as_posix())


def _object(value: Any, label: str) -> dict[str, Any]:
    """Require a decoded JSON object.

    Args:
        value: Candidate decoded value.
        label: Privacy-safe diagnostic label.

    Returns:
        Typed object.

    Raises:
        PublicAuditError: If ``value`` is not an object.

    """
    if not isinstance(value, dict):
        raise PublicAuditError(f"public {label} must be a JSON object")
    return value


def _string(value: Any, label: str) -> str:
    """Require one non-empty public metadata string.

    Args:
        value: Candidate decoded value.
        label: Privacy-safe diagnostic label.

    Returns:
        Validated string.

    Raises:
        PublicAuditError: If ``value`` is not non-empty text.

    """
    if not isinstance(value, str) or not value:
        raise PublicAuditError(f"public {label} must be a non-empty string")
    return value


__all__ = ["build_manifest", "load_manifest"]

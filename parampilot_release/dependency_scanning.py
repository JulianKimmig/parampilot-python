"""Strict registry-only dependency metadata checks for public SDK releases."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, NoReturn

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from parampilot_release.errors import PublicAuditError
from parampilot_release.lock_artifacts import validate_registry_artifacts


def scan_public_dependencies(root: Path) -> None:
    """Reject malformed, overridden, direct, local, or non-PyPI dependencies.

    Args:
        root: Candidate public source root containing project and lock metadata.

    Raises:
        PublicAuditError: If dependency structure or source provenance is unsafe.

    """
    pyproject, lock = _load_metadata(root)
    _reject_uv_source_overrides(pyproject)
    for requirement in _requirements_from_pyproject(pyproject):
        if _is_non_registry_requirement(requirement):
            raise PublicAuditError(
                "public dependency metadata contains a non-registry dependency"
            )
    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        _raise_invalid_metadata()
    for package in packages:
        _validate_lock_source(package)


def _load_metadata(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the public project and lock TOML documents.

    Args:
        root: Candidate public source root.

    Returns:
        Parsed pyproject and uv lock objects.

    Raises:
        PublicAuditError: If either document is absent or invalid TOML.

    """
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PublicAuditError(
            "public dependency metadata is missing or invalid"
        ) from error
    return pyproject, lock


def _reject_uv_source_overrides(pyproject: dict[str, Any]) -> None:
    """Reject uv source or index overrides outside the PyPI-only contract.

    Args:
        pyproject: Parsed public project metadata.

    Raises:
        PublicAuditError: If a uv source or index override is declared.

    """
    tool = _mapping(pyproject.get("tool", {}))
    uv_value = tool.get("uv")
    if uv_value is None:
        return
    uv = _mapping(uv_value)
    if "sources" in uv or "index" in uv:
        raise PublicAuditError(
            "public dependency metadata contains a uv source override"
        )


def _requirements_from_pyproject(value: dict[str, Any]) -> tuple[str, ...]:
    """Collect validated project, build, optional, and development requirements.

    Args:
        value: Parsed ``pyproject.toml`` object.

    Returns:
        All direct requirement strings across public dependency groups.

    Raises:
        PublicAuditError: If dependency metadata has an unexpected shape.

    """
    project = _mapping(value.get("project"))
    _text(project.get("name"))
    _text(project.get("version"))
    requirements = list(_strings(project.get("dependencies", [])))
    optional = _mapping(project.get("optional-dependencies", {}))
    for group in optional.values():
        requirements.extend(_strings(group))
    build = _mapping(value.get("build-system"))
    requirements.extend(_strings(build.get("requires")))
    groups = _mapping(value.get("dependency-groups", {}))
    for group in groups.values():
        requirements.extend(_strings(group))
    return tuple(requirements)


def _is_non_registry_requirement(requirement: str) -> bool:
    """Return whether a requirement names a direct, URL, or local source.

    Args:
        requirement: PEP 508-like direct requirement text.

    Returns:
        Whether the requirement bypasses the approved public registry.

    """
    lowered = requirement.lower().strip()
    return (
        "@" in lowered
        or "://" in lowered
        or "git+" in lowered
        or "file:" in lowered
        or lowered.startswith(("-e ", "--editable ", "./", "../", "/"))
    )


def _validate_lock_source(package: Any) -> None:
    """Require one well-formed PyPI package or the public editable root.

    Args:
        package: Parsed uv lock package entry.

    Raises:
        PublicAuditError: If package identity or source provenance is invalid.

    """
    if not isinstance(package, dict):
        _raise_invalid_metadata()
    name = _text(package.get("name"))
    _text(package.get("version"))
    source = package.get("source")
    if source == {"registry": "https://pypi.org/simple"}:
        validate_registry_artifacts(package)
        return
    if name == "parampilot" and source == {"editable": "."}:
        return
    raise PublicAuditError("public dependency lock contains a non-registry source")


def _mapping(value: Any) -> dict[str, Any]:
    """Return a string-keyed metadata mapping or fail safely.

    Args:
        value: Candidate parsed TOML value.

    Returns:
        Validated mapping.

    Raises:
        PublicAuditError: If the value is not a string-keyed mapping.

    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _raise_invalid_metadata()
    return value


def _strings(value: Any) -> tuple[str, ...]:
    """Return a validated sequence of non-empty requirement strings.

    Args:
        value: Candidate parsed TOML array.

    Returns:
        Requirement strings.

    Raises:
        PublicAuditError: If the value is not a string array.

    """
    if not isinstance(value, list):
        _raise_invalid_metadata()
    return tuple(_text(item) for item in value)


def _text(value: Any) -> str:
    """Return one non-empty metadata string or fail safely.

    Args:
        value: Candidate parsed TOML scalar.

    Returns:
        Non-empty string.

    Raises:
        PublicAuditError: If the value is not non-empty text.

    """
    if not isinstance(value, str) or not value.strip():
        _raise_invalid_metadata()
    return value


def _raise_invalid_metadata() -> NoReturn:
    """Raise the stable dependency-metadata structural failure.

    Raises:
        PublicAuditError: Always.

    """
    raise PublicAuditError("public dependency metadata is missing or invalid")


__all__ = ["scan_public_dependencies"]

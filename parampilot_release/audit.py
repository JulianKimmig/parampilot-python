"""Exact manifest, content, dependency, and history-boundary public audit."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from parampilot_release.configuration import (
    ALLOWLIST_VERSION,
    MANIFEST_NAME,
    is_safe_public_path,
    load_public_source_allowlist,
)
from parampilot_release.errors import PublicAuditError
from parampilot_release.hashing import render_json, sha256_file
from parampilot_release.manifest import build_manifest, load_manifest
from parampilot_release.models import AuditReport
from parampilot_release.scanning import scan_public_files

COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def audit_public_tree(
    public_root: Path,
    *,
    denied_literals: Iterable[str] = (),
) -> AuditReport:
    """Verify exact public paths, bytes, provenance, content, and dependencies.

    Args:
        public_root: Extracted public source tree.
        denied_literals: Additional owner-supplied private text fragments.

    Returns:
        Successful audit identity.

    Raises:
        PublicAuditError: If any release boundary is invalid.

    """
    if public_root.is_symlink():
        raise PublicAuditError("public extraction root must not be a symlink")
    root = public_root.resolve()
    if not root.is_dir():
        raise PublicAuditError("public extraction root is missing")
    if (root / ".git").exists() or (root / ".git").is_symlink():
        raise PublicAuditError("public extraction must contain no Git history")
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink():
        raise PublicAuditError("public extraction manifest must not be a symlink")
    manifest = load_manifest(manifest_path)
    if manifest_path.read_bytes() != render_json(manifest):
        raise PublicAuditError("public extraction manifest must be canonical JSON")
    source_commit = _manifest_string(manifest, "source_commit")
    if not COMMIT_PATTERN.fullmatch(source_commit):
        raise PublicAuditError("public manifest source commit is invalid")
    if manifest.get("format_version") != 1:
        raise PublicAuditError("public manifest format version is unsupported")
    if manifest.get("allowlist_version") != ALLOWLIST_VERSION:
        raise PublicAuditError("public manifest allowlist version is unsupported")
    expected = _manifest_files(manifest)
    actual = _actual_files(root)
    expected_paths = set(expected)
    actual_paths = set(actual)
    approved_paths = {path.as_posix() for path in load_public_source_allowlist(root)}
    missing = sorted(expected_paths - actual_paths)
    unexpected = sorted(actual_paths - expected_paths)
    if missing:
        raise PublicAuditError("a public manifest file is missing")
    if unexpected:
        raise PublicAuditError("the public tree contains an unexpected file")
    unapproved = sorted(expected_paths - approved_paths)
    if unapproved:
        raise PublicAuditError("the public manifest contains an unapproved file")
    allowlisted_missing = sorted(approved_paths - expected_paths)
    if allowlisted_missing:
        raise PublicAuditError("an allowlisted public file is missing")
    for relative, metadata in expected.items():
        path = actual[relative]
        if path.stat().st_size != metadata["bytes"]:
            raise PublicAuditError("a public file size does not match its manifest")
        if sha256_file(path) != metadata["sha256"]:
            raise PublicAuditError("a public file hash does not match its manifest")
    relative_paths = tuple(PurePosixPath(path) for path in sorted(expected))
    _validate_release_metadata(manifest, root, relative_paths, source_commit)
    scan_public_files(root, relative_paths, denied_literals=denied_literals)
    return AuditReport(
        manifest_sha256=sha256_file(manifest_path),
        source_commit=source_commit,
        file_count=len(expected),
    )


def _validate_release_metadata(
    manifest: dict[str, Any],
    root: Path,
    relative_paths: tuple[PurePosixPath, ...],
    source_commit: str,
) -> None:
    """Recompute contract, generator, and package manifest descriptions.

    Args:
        manifest: Decoded public manifest under audit.
        root: Extracted public root.
        relative_paths: Exact sorted manifest file paths.
        source_commit: Validated source identity from the manifest.

    Raises:
        PublicAuditError: If self-described release metadata differs from bytes.

    """
    recomputed = build_manifest(root, relative_paths, source_commit)
    for key in ("schema", "generator", "package"):
        if manifest.get(key) != recomputed[key]:
            raise PublicAuditError(f"public manifest {key} metadata is inconsistent")
    if manifest != recomputed:
        raise PublicAuditError("public manifest metadata is inconsistent")


def _manifest_files(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate and index manifest file entries.

    Args:
        manifest: Decoded public manifest.

    Returns:
        Path-keyed file metadata.

    Raises:
        PublicAuditError: If entries are malformed or duplicated.

    """
    values = manifest.get("files")
    if not isinstance(values, list) or not values:
        raise PublicAuditError("public manifest files must be a non-empty list")
    indexed: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise PublicAuditError("public manifest contains an invalid file entry")
        relative = value.get("path")
        size = value.get("bytes")
        digest = value.get("sha256")
        if not isinstance(relative, str) or not is_safe_public_path(relative):
            raise PublicAuditError("public manifest contains an unsafe file path")
        if relative == MANIFEST_NAME or relative in indexed:
            raise PublicAuditError("public manifest contains a duplicate file path")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise PublicAuditError("public manifest contains an invalid file size")
        if not isinstance(digest, str) or not HASH_PATTERN.fullmatch(digest):
            raise PublicAuditError("public manifest contains an invalid file hash")
        indexed[relative] = {"bytes": size, "sha256": digest}
    if list(indexed) != sorted(indexed):
        raise PublicAuditError("public manifest file entries must be sorted")
    return indexed


def _actual_files(root: Path) -> dict[str, Path]:
    """Index regular files and reject every symlink in a public tree.

    Args:
        root: Public extraction root.

    Returns:
        Relative path to local regular-file mapping, excluding the manifest.

    Raises:
        PublicAuditError: If a symlink or non-file leaf is present.

    """
    values: dict[str, Path] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise PublicAuditError("the public tree contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise PublicAuditError("the public tree contains a non-file entry")
        if relative != MANIFEST_NAME:
            values[relative] = path
    return values


def _manifest_string(manifest: dict[str, Any], key: str) -> str:
    """Return one required non-empty string from a manifest.

    Args:
        manifest: Decoded manifest object.
        key: Required field name.

    Returns:
        Required string value.

    Raises:
        PublicAuditError: If the field is absent or invalid.

    """
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise PublicAuditError(f"public manifest {key} is invalid")
    return value


__all__ = ["audit_public_tree"]

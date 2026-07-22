"""Deterministic allowlisted public-tree extraction without private history."""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from parampilot_release.audit import audit_public_tree
from parampilot_release.configuration import (
    MANIFEST_NAME,
    load_public_source_allowlist,
)
from parampilot_release.errors import PublicExtractionError
from parampilot_release.git_source import (
    committed_package_bytes,
    tracked_package_paths,
    validate_source_repository,
)
from parampilot_release.hashing import render_json, sha256_bytes
from parampilot_release.manifest import build_manifest
from parampilot_release.models import ExtractionResult
from parampilot_release.scanning import scan_public_files


def extract_public_tree(
    *,
    repository_root: Path,
    output_root: Path,
    expected_commit: str,
    denied_literals: Iterable[str] = (),
) -> ExtractionResult:
    """Copy one clean private commit into a new audited history-free tree.

    Args:
        repository_root: Private monorepo Git top level.
        output_root: New destination outside the private repository.
        expected_commit: Exact full source commit approved for extraction.
        denied_literals: Additional private host or organization text to reject.

    Returns:
        Exact extraction manifest identity.

    Raises:
        PublicExtractionError: If source, allowlist, or destination safety fails.
        PublicAuditError: If copied content or dependency boundaries fail.

    """
    repository = repository_root.resolve()
    output = output_root.resolve()
    _validate_destination(repository, output_root, output)
    package_root, source_commit = validate_source_repository(
        repository,
        expected_commit,
    )
    paths = tracked_package_paths(repository)
    allowlist = load_public_source_allowlist(package_root)
    _validate_allowlist(package_root, paths, allowlist)
    denied = tuple(denied_literals)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-",
        dir=output.parent,
    ) as temporary:
        temporary_root = Path(temporary) / "public-tree"
        temporary_root.mkdir()
        _copy_files(
            repository,
            temporary_root,
            paths,
            source_commit,
        )
        scan_public_files(temporary_root, paths, denied_literals=denied)
        manifest = build_manifest(temporary_root, paths, source_commit)
        manifest_bytes = render_json(manifest)
        (temporary_root / MANIFEST_NAME).write_bytes(manifest_bytes)
        audit_public_tree(temporary_root, denied_literals=denied)
        temporary_root.replace(output)
    return ExtractionResult(
        manifest_path=output / MANIFEST_NAME,
        manifest_sha256=sha256_bytes(manifest_bytes),
        source_commit=source_commit,
        file_count=len(paths),
    )


def _validate_destination(
    repository_root: Path,
    raw_output: Path,
    resolved_output: Path,
) -> None:
    """Require a new destination outside the private repository.

    Args:
        repository_root: Resolved private repository root.
        raw_output: Caller-provided destination before resolution.
        resolved_output: Resolved destination.

    Raises:
        PublicExtractionError: If ownership or history isolation is ambiguous.

    """
    if raw_output.exists() or raw_output.is_symlink():
        raise PublicExtractionError("public output path must not exist")
    if not resolved_output.parent.is_dir():
        raise PublicExtractionError("public output parent directory must exist")
    if resolved_output.is_relative_to(repository_root):
        raise PublicExtractionError(
            "public output must be outside the private repository"
        )


def _validate_allowlist(
    package_root: Path,
    paths: tuple[PurePosixPath, ...],
    allowlist: tuple[PurePosixPath, ...],
) -> None:
    """Require every tracked package file to be reviewed and non-symlinked.

    Args:
        package_root: Validated private SDK package root.
        paths: Tracked package-relative paths.
        allowlist: Exact reviewed package-relative source paths.

    Raises:
        PublicExtractionError: If a file is unreviewed, absent, or a symlink.

    """
    if not paths:
        raise PublicExtractionError("public extraction allowlist resolved no files")
    tracked = set(paths)
    approved = set(allowlist)
    unexpected = sorted(tracked - approved, key=PurePosixPath.as_posix)
    if unexpected:
        raise PublicExtractionError(
            "one or more tracked SDK paths are outside the public allowlist"
        )
    missing = sorted(approved - tracked, key=PurePosixPath.as_posix)
    if missing:
        raise PublicExtractionError("an allowlisted public path is not tracked")
    for relative_path in paths:
        path = package_root.joinpath(*relative_path.parts)
        if path.is_symlink():
            raise PublicExtractionError("a tracked public symlink is prohibited")
        if not path.is_file():
            raise PublicExtractionError("a tracked public file is missing")


def _copy_files(
    repository_root: Path,
    output_root: Path,
    paths: tuple[PurePosixPath, ...],
    source_commit: str,
) -> None:
    """Copy exact committed Git blobs into a fresh directory hierarchy.

    Args:
        repository_root: Validated private Git repository root.
        output_root: New temporary public root.
        paths: Sorted allowlisted relative paths.
        source_commit: Exact full source commit selected for extraction.

    """
    for relative_path in paths:
        destination = output_root.joinpath(*relative_path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            committed_package_bytes(
                repository_root,
                source_commit,
                relative_path,
            )
        )
        destination.chmod(0o644)


__all__ = ["extract_public_tree"]

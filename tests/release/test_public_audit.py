"""Manifest integrity tests for an extracted public SDK tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from parampilot_release.audit import audit_public_tree
from parampilot_release.errors import PublicAuditError
from parampilot_release.extraction import extract_public_tree
from tests.release.support import CommittedSdkRepository


def _extract(
    repository: CommittedSdkRepository,
    output: Path,
) -> Path:
    """Extract one committed fixture and return the public root.

    Args:
        repository: Clean committed SDK fixture.
        output: New public destination.

    Returns:
        Extracted public root.

    """
    extract_public_tree(
        repository_root=repository.root,
        output_root=output,
        expected_commit=repository.commit,
    )
    return output


def test_audit_accepts_exact_manifest_and_rejects_tamper_or_extra_file(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Manifest validation must prove exact paths and bytes.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")

    report = audit_public_tree(public_root)

    assert report.file_count > 50
    assert report.source_commit == committed_sdk_repository.commit
    assert len(report.manifest_sha256) == 64

    (public_root / "README.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(PublicAuditError, match="hash|size"):
        audit_public_tree(public_root)

    restored_root = _extract(committed_sdk_repository, tmp_path / "public-two")
    (restored_root / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(PublicAuditError, match="unexpected"):
        audit_public_tree(restored_root)


def test_audit_recomputes_schema_and_generator_manifest_metadata(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Self-described contract metadata cannot disagree with extracted bytes.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    manifest_path = public_root / ".parampilot-public-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"]["sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PublicAuditError, match="schema"):
        audit_public_tree(public_root)


def test_audit_rejects_unknown_manifest_metadata(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Unscanned or owner-invented manifest fields cannot cross the boundary.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    manifest_path = public_root / ".parampilot-public-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["private_origin"] = "/".join(("", "home", "owner", "private-parampilot"))
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PublicAuditError, match="metadata"):
        audit_public_tree(public_root)


def test_audit_rejects_noncanonical_manifest_bytes(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Semantically hidden duplicate or whitespace content must not survive.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    manifest_path = public_root / ".parampilot-public-manifest.json"
    manifest_path.write_bytes(b" " + manifest_path.read_bytes())

    with pytest.raises(PublicAuditError, match="canonical"):
        audit_public_tree(public_root)


def test_audit_rejects_duplicate_manifest_keys(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Duplicate JSON keys must not survive canonical manifest validation.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    manifest_path = public_root / ".parampilot-public-manifest.json"
    canonical = manifest_path.read_text(encoding="utf-8")
    duplicated = canonical.replace(
        '  "format_version": 1,\n',
        '  "format_version": 1,\n  "format_version": 1,\n',
        1,
    )
    assert duplicated != canonical
    manifest_path.write_text(duplicated, encoding="utf-8")

    with pytest.raises(PublicAuditError, match="canonical"):
        audit_public_tree(public_root)


def test_audit_rejects_symlinked_public_root(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """The audited root itself must be an owned directory, not an alias.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    alias = tmp_path / "public-alias"
    alias.symlink_to(public_root, target_is_directory=True)

    with pytest.raises(PublicAuditError, match="symlink"):
        audit_public_tree(alias)


@pytest.mark.parametrize(
    "unsafe_path",
    ["..\\escape", "C:/escape", "docs/unsafe\tname.md", "CON"],
)
def test_audit_rejects_cross_platform_unsafe_manifest_path(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    """Manifest paths with platform-specific separators must fail as unsafe.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        unsafe_path: Platform-sensitive path to reject.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    manifest_path = public_root / ".parampilot-public-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = unsafe_path
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PublicAuditError, match="unsafe"):
        audit_public_tree(public_root)


def test_audit_rejects_non_utf8_manifest_safely(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Invalid manifest encoding must remain a typed boundary failure.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    manifest_path = public_root / ".parampilot-public-manifest.json"
    manifest_path.write_bytes(b"\xff\xfe")

    with pytest.raises(PublicAuditError, match="manifest"):
        audit_public_tree(public_root)


def test_audit_rejects_non_utf8_manifested_json_safely(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Manifest-consistent invalid JSON bytes must not escape as a traceback.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    public_root = _extract(committed_sdk_repository, tmp_path / "public")
    manifest_path = public_root / ".parampilot-public-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema_path = public_root / "contracts" / "programmatic-openapi.json"
    invalid_bytes = b"\xff\xfe"
    schema_path.write_bytes(invalid_bytes)
    schema_entry = next(
        entry
        for entry in manifest["files"]
        if entry["path"] == "contracts/programmatic-openapi.json"
    )
    schema_entry["bytes"] = len(invalid_bytes)
    schema_entry["sha256"] = hashlib.sha256(invalid_bytes).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PublicAuditError, match="JSON"):
        audit_public_tree(public_root)

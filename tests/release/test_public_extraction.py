"""Behavior tests for deterministic history-isolated public extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parampilot_release.errors import PublicExtractionError
from parampilot_release.extraction import extract_public_tree
from tests.release.support import CommittedSdkRepository


def test_clean_committed_tree_extracts_reproducibly_without_git_history(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Two outputs from one commit must have identical manifests and no Git data.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    first_root = tmp_path / "public-one"
    second_root = tmp_path / "public-two"

    first = extract_public_tree(
        repository_root=committed_sdk_repository.root,
        output_root=first_root,
        expected_commit=committed_sdk_repository.commit,
    )
    second = extract_public_tree(
        repository_root=committed_sdk_repository.root,
        output_root=second_root,
        expected_commit=committed_sdk_repository.commit,
    )

    assert first.manifest_sha256 == second.manifest_sha256
    assert first.file_count == second.file_count
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert not (first_root / ".git").exists()
    assert (first_root / ".github" / "workflows" / "ci.yml").is_file()
    assert (first_root / "src" / "parampilot" / "py.typed").is_file()
    assert not list(first_root.rglob("__pycache__"))
    assert not list(first_root.rglob("*.pyc"))
    assert not (first_root / ".venv").exists()
    assert not (first_root / "dist").exists()

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_commit"] == committed_sdk_repository.commit
    assert manifest["format_version"] == 1
    assert manifest["allowlist_version"] == 1
    assert manifest["allowlist"]["path"] == ("contracts/public-source-allowlist.txt")
    assert len(manifest["allowlist"]["sha256"]) == 64
    assert manifest["schema"]["path"] == "contracts/programmatic-openapi.json"
    assert manifest["generator"]["path"] == ("src/parampilot/generated/provenance.json")
    assert all(not entry["path"].startswith("/") for entry in manifest["files"])
    assert str(committed_sdk_repository.root) not in first.manifest_path.read_text()


def test_extraction_copies_committed_bytes_not_smudged_worktree_bytes(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """A clean filtered checkout must still extract exact Git blob bytes.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture with CRLF rules.
        tmp_path: Pytest-managed scratch directory.

    """
    relative_path = "README.md"
    readme = committed_sdk_repository.package / relative_path
    committed = committed_sdk_repository.committed_package_bytes(relative_path)
    readme.write_bytes(committed.replace(b"\n", b"\r\n"))
    assert b"\r\n" in readme.read_bytes()
    committed_sdk_repository.refresh_package_path(relative_path)
    assert committed_sdk_repository.git_status() == ""

    public_root = tmp_path / "public"
    extract_public_tree(
        repository_root=committed_sdk_repository.root,
        output_root=public_root,
        expected_commit=committed_sdk_repository.commit,
    )

    assert (public_root / relative_path).read_bytes() == committed


def test_extraction_rejects_dirty_source_before_creating_output(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Uncommitted SDK changes must stop extraction before any destination exists.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    output = tmp_path / "public"
    (committed_sdk_repository.package / "README.md").write_text(
        "uncommitted\n", encoding="utf-8"
    )

    with pytest.raises(PublicExtractionError, match="clean"):
        extract_public_tree(
            repository_root=committed_sdk_repository.root,
            output_root=output,
            expected_commit=committed_sdk_repository.commit,
        )

    assert not output.exists()


def test_extraction_rejects_dirty_file_outside_sdk_package(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """The whole identified private commit, not only the SDK subtree, must be clean.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    output = tmp_path / "public"
    (committed_sdk_repository.root / "private-backend-change.txt").write_text(
        "uncommitted\n",
        encoding="utf-8",
    )

    with pytest.raises(PublicExtractionError, match="clean"):
        extract_public_tree(
            repository_root=committed_sdk_repository.root,
            output_root=output,
            expected_commit=committed_sdk_repository.commit,
        )

    assert not output.exists()


def test_extraction_rejects_wrong_commit_and_existing_destination(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Extraction identity and destination ownership must be explicit.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    output = tmp_path / "public"
    with pytest.raises(PublicExtractionError, match="commit"):
        extract_public_tree(
            repository_root=committed_sdk_repository.root,
            output_root=output,
            expected_commit="0" * 40,
        )
    assert not output.exists()

    output.mkdir()
    with pytest.raises(PublicExtractionError, match="must not exist"):
        extract_public_tree(
            repository_root=committed_sdk_repository.root,
            output_root=output,
            expected_commit=committed_sdk_repository.commit,
        )


def test_extraction_rejects_unreviewed_nested_file_and_symlink(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Tracked paths outside the allowlist and escaping links must stop release.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    extra_path = committed_sdk_repository.package / "docs" / "private-notes.md"
    extra_path.write_text("private\n", encoding="utf-8")
    with_extra = committed_sdk_repository.commit_all("add unexpected file")
    with pytest.raises(PublicExtractionError, match="allowlist"):
        extract_public_tree(
            repository_root=with_extra.root,
            output_root=tmp_path / "unexpected-output",
            expected_commit=with_extra.commit,
        )

    extra_path.unlink()
    target = tmp_path / "outside.txt"
    target.write_text("outside\n", encoding="utf-8")
    link = with_extra.package / "docs" / "quickstart.md"
    link.unlink()
    link.symlink_to(target)
    with_link = with_extra.commit_all("replace unexpected file with symlink")
    with pytest.raises(PublicExtractionError, match="symlink"):
        extract_public_tree(
            repository_root=with_link.root,
            output_root=tmp_path / "symlink-output",
            expected_commit=with_link.commit,
        )


def test_extraction_does_not_echo_unreviewed_sensitive_filename(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Unexpected source-path diagnostics must not disclose credential text.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    credential = "owa_" + "pat-" + "abcdefghijklmnopqrstuvwxyz0123456789"
    unexpected = committed_sdk_repository.package / "docs" / f"{credential}.md"
    unexpected.write_text("safe content\n", encoding="utf-8")
    contaminated = committed_sdk_repository.commit_all("add unreviewed filename")

    with pytest.raises(PublicExtractionError, match="allowlist") as failure:
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )

    assert credential not in str(failure.value)

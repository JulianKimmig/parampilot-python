"""Exact public-source allowlist validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from parampilot_release.errors import PublicAuditError
from parampilot_release.extraction import extract_public_tree
from tests.release.support import CommittedSdkRepository


def _allowlist_path(repository: CommittedSdkRepository) -> Path:
    """Return the fixture's reviewed public-source allowlist path.

    Args:
        repository: Clean committed SDK fixture.

    Returns:
        Path to the exact public-source allowlist.

    """
    return repository.package / "contracts" / "public-source-allowlist.txt"


@pytest.mark.parametrize(
    "unsafe_path",
    ["..\\escape", "C:/escape", "docs/unsafe\tname.md", "CON"],
)
def test_extraction_rejects_cross_platform_unsafe_allowlist_path(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    """Platform-sensitive paths must not acquire escape semantics.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        unsafe_path: Platform-sensitive path to reject.

    """
    allowlist = _allowlist_path(committed_sdk_repository)
    lines = allowlist.read_text(encoding="utf-8").splitlines()
    comments = [line for line in lines if line.startswith("#")]
    entries = [line for line in lines if line and not line.startswith("#")]
    entries.append(unsafe_path)
    allowlist.write_text(
        "\n".join([*comments, *sorted(entries), ""]),
        encoding="utf-8",
    )
    contaminated = committed_sdk_repository.commit_all("add unsafe allowlist path")

    with pytest.raises(PublicAuditError, match="unsafe"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )


@pytest.mark.parametrize("decorated_path", [" README.md", "README.md "])
def test_extraction_rejects_noncanonical_allowlist_whitespace(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    decorated_path: str,
) -> None:
    """Allowlist entries must be exact lines rather than trimmed aliases.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        decorated_path: Noncanonical rendering of an approved path.

    """
    allowlist = _allowlist_path(committed_sdk_repository)
    text = allowlist.read_text(encoding="utf-8")
    allowlist.write_text(
        text.replace("README.md\n", f"{decorated_path}\n", 1),
        encoding="utf-8",
    )
    contaminated = committed_sdk_repository.commit_all("decorate allowlist path")

    with pytest.raises(PublicAuditError, match="normalized"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )


def test_extraction_rejects_removed_required_security_gate(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """A reviewed source set cannot silently delete its security test gate.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    relative = "tests/release/test_content_scanning.py"
    (committed_sdk_repository.package / relative).unlink()
    allowlist = _allowlist_path(committed_sdk_repository)
    lines = allowlist.read_text(encoding="utf-8").splitlines()
    allowlist.write_text(
        "\n".join([line for line in lines if line != relative]) + "\n",
        encoding="utf-8",
    )
    contaminated = committed_sdk_repository.commit_all("remove security gate")

    with pytest.raises(PublicAuditError, match="required public allowlist path"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )

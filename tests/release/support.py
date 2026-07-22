"""Actual-Git fixtures for history-isolated public extraction tests."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class CommittedSdkRepository:
    """Temporary private-style repository containing one committed SDK tree.

    Args:
        root: Temporary repository root.
        package: SDK package root under ``packages/parampilot-api``.
        commit: Current exact source commit.

    """

    root: Path
    package: Path
    commit: str

    def commit_all(self, message: str) -> CommittedSdkRepository:
        """Commit every package change and return the updated fixture value.

        Args:
            message: Local fixture commit message.

        Returns:
            Fixture value with the new exact commit identity.

        """
        _git(self.root, "add", "packages/parampilot-api")
        _git(self.root, "commit", "-q", "-m", message)
        return CommittedSdkRepository(
            root=self.root,
            package=self.package,
            commit=_git(self.root, "rev-parse", "HEAD"),
        )

    def git_status(self) -> str:
        """Return the complete porcelain status of the temporary repository.

        Returns:
            Stable status text, empty when the fixture repository is clean.

        """
        return _git(self.root, "status", "--porcelain=v1", "--untracked-files=all")

    def committed_package_bytes(self, relative_path: str) -> bytes:
        """Read exact committed bytes for one SDK package path.

        Args:
            relative_path: POSIX path relative to the SDK package root.

        Returns:
            Raw bytes stored in the fixture's current Git commit.

        """
        return _git_bytes(
            self.root,
            "show",
            f"HEAD:packages/parampilot-api/{relative_path}",
        )

    def refresh_package_path(self, relative_path: str) -> None:
        """Refresh Git's index metadata for a filter-equivalent worktree file.

        Args:
            relative_path: POSIX path relative to the SDK package root.

        Returns:
            None.

        """
        _git(self.root, "add", f"packages/parampilot-api/{relative_path}")


def _git(root: Path, *arguments: str) -> str:
    """Run Git inside one isolated fixture repository.

    Args:
        root: Repository working tree.
        *arguments: Git arguments after the executable.

    Returns:
        Stripped standard output.

    """
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_bytes(root: Path, *arguments: str) -> bytes:
    """Run Git in one fixture repository and return raw standard output.

    Args:
        root: Repository working tree.
        *arguments: Git arguments after the executable.

    Returns:
        Exact standard-output bytes.

    """
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return result.stdout


@pytest.fixture
def committed_sdk_repository(tmp_path: Path) -> CommittedSdkRepository:
    """Create a clean real Git repository containing the current SDK sources.

    Args:
        tmp_path: Pytest-managed scratch directory.

    Returns:
        Clean committed SDK repository fixture.

    """
    root = tmp_path / "private-source"
    package = root / "packages" / "parampilot-api"
    root.mkdir()
    shutil.copytree(
        PACKAGE_ROOT,
        package,
        ignore=shutil.ignore_patterns(
            ".git",
            ".mypy_cache",
            ".parampilot-public-manifest.json",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "dist",
            "*.egg-info",
            "*.pyc",
        ),
    )
    (root / ".gitattributes").write_text(
        "packages/parampilot-api/README.md text eol=crlf\n",
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "release-fixture@example.invalid")
    _git(root, "config", "user.name", "Release Fixture")
    _git(root, "add", ".gitattributes", "packages/parampilot-api")
    _git(root, "commit", "-q", "-m", "fixture")
    return CommittedSdkRepository(
        root=root,
        package=package,
        commit=_git(root, "rev-parse", "HEAD"),
    )

"""Read-only Git identity and tracked-file boundaries for public extraction."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from parampilot_release.configuration import PRIVATE_PACKAGE_PATH
from parampilot_release.errors import PublicExtractionError

COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


def validate_source_repository(
    repository_root: Path,
    expected_commit: str,
) -> tuple[Path, str]:
    """Require an exact clean private commit and return its SDK package root.

    Args:
        repository_root: Candidate private repository root.
        expected_commit: Exact full commit hash approved for extraction.

    Returns:
        Resolved package root and normalized current commit.

    Raises:
        PublicExtractionError: If identity, cleanliness, or package layout fails.

    """
    root = repository_root.resolve()
    top_level = _git(root, "rev-parse", "--show-toplevel")
    if Path(top_level).resolve() != root:
        raise PublicExtractionError("repository_root must be the Git top level")
    commit = _git(root, "rev-parse", "HEAD").lower()
    if not COMMIT_PATTERN.fullmatch(expected_commit.lower()):
        raise PublicExtractionError("expected source commit must be a full Git hash")
    if commit != expected_commit.lower():
        raise PublicExtractionError(
            "current source commit does not match expected commit"
        )
    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status:
        raise PublicExtractionError(
            "private source tree must be clean before extraction"
        )
    package_root = root.joinpath(*PRIVATE_PACKAGE_PATH.parts)
    if not package_root.is_dir():
        raise PublicExtractionError("approved private SDK package path is missing")
    return package_root, commit


def tracked_package_paths(repository_root: Path) -> tuple[PurePosixPath, ...]:
    """List stable package-relative files tracked by Git.

    Args:
        repository_root: Validated private repository root.

    Returns:
        Sorted package-relative POSIX paths.

    """
    output = _git(
        repository_root.resolve(),
        "ls-files",
        "-z",
        "--",
        PRIVATE_PACKAGE_PATH.as_posix(),
    )
    prefix = f"{PRIVATE_PACKAGE_PATH.as_posix()}/"
    values: list[PurePosixPath] = []
    for raw_path in output.split("\0"):
        if not raw_path:
            continue
        if not raw_path.startswith(prefix):
            raise PublicExtractionError("Git returned a path outside the SDK package")
        values.append(PurePosixPath(raw_path.removeprefix(prefix)))
    return tuple(sorted(values, key=PurePosixPath.as_posix))


def committed_package_bytes(
    repository_root: Path,
    source_commit: str,
    relative_path: PurePosixPath,
) -> bytes:
    """Read exact SDK file bytes from one validated Git commit.

    Args:
        repository_root: Validated private repository root.
        source_commit: Exact full source commit selected for extraction.
        relative_path: Normalized SDK package-relative path.

    Returns:
        Raw blob bytes stored in the selected commit.

    Raises:
        PublicExtractionError: If Git cannot read the committed blob.

    """
    object_name = (
        f"{source_commit}:{PRIVATE_PACKAGE_PATH.as_posix()}/{relative_path.as_posix()}"
    )
    return _git_bytes(
        repository_root.resolve(),
        "cat-file",
        "blob",
        object_name,
    )


def _git(root: Path, *arguments: str) -> str:
    """Run one read-only Git command with a privacy-safe failure.

    Args:
        root: Repository root.
        *arguments: Git arguments after the executable.

    Returns:
        Standard output with trailing whitespace removed.

    Raises:
        PublicExtractionError: If Git cannot establish release identity.

    """
    executable = shutil.which("git")
    if executable is None:
        raise PublicExtractionError(
            "Git is required to validate release source identity"
        )
    try:
        result = subprocess.run(  # noqa: S603 - fixed Git plus internal arguments only
            [executable, *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, UnicodeError, subprocess.CalledProcessError) as error:
        raise PublicExtractionError(
            "Git could not validate release source identity"
        ) from error
    return result.stdout.rstrip("\n")


def _git_bytes(root: Path, *arguments: str) -> bytes:
    """Run one read-only Git command and return privacy-safe raw output.

    Args:
        root: Repository root.
        *arguments: Git arguments after the executable.

    Returns:
        Exact standard-output bytes.

    Raises:
        PublicExtractionError: If Git cannot read committed source bytes.

    """
    executable = shutil.which("git")
    if executable is None:
        raise PublicExtractionError(
            "Git is required to validate release source identity"
        )
    try:
        result = subprocess.run(  # noqa: S603 - fixed Git plus internal arguments only
            [executable, *arguments],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PublicExtractionError(
            "Git could not read committed public source bytes"
        ) from error
    return result.stdout


__all__ = [
    "committed_package_bytes",
    "tracked_package_paths",
    "validate_source_repository",
]

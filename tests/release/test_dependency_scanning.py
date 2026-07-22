"""Registry-only dependency and lock-artifact extraction tests."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from parampilot_release.errors import PublicAuditError
from parampilot_release.extraction import extract_public_tree
from tests.release.support import CommittedSdkRepository


def test_extraction_rejects_non_registry_dependency(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Local, editable, URL, and private-Git requirements cannot be public inputs.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    pyproject = committed_sdk_repository.package / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(
        text.replace(
            "dependencies = [",
            'dependencies = [\n    "private-sdk @ git+ssh://git@example.invalid/sdk",',
            1,
        ),
        encoding="utf-8",
    )
    contaminated = committed_sdk_repository.commit_all("add private dependency")

    with pytest.raises(PublicAuditError, match="dependency"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )


@pytest.mark.parametrize(
    ("pattern", "replacement"),
    [
        (
            r'url = "https://files\.pythonhosted\.org/',
            'url = "https://private-packages.example/',
        ),
        (
            r'url = "https://files\.pythonhosted\.org/',
            'url = "https://files.pythonhosted.org.evil.example/',
        ),
        (
            r'url = "https://files\.pythonhosted\.org/',
            'url = "https://user@files.pythonhosted.org/',
        ),
        (
            r'url = "https://files\.pythonhosted\.org/',
            'url = "https://files.pythonhosted.org:443/',
        ),
        (
            r'url = "https://files\.pythonhosted\.org/packages/',
            'url = "https://files.pythonhosted.org/packages?mirror=/',
        ),
        (
            r'url = "https://files\.pythonhosted\.org/packages/',
            r'url = "https://files.pythonhosted.org/packages/\\n',
        ),
        (r'hash = "sha256:[0-9a-f]{64}"', 'hash = "sha256:invalid"'),
        (r"size = [1-9][0-9]*", "size = 0"),
    ],
)
def test_extraction_rejects_invalid_registry_artifact_metadata(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    pattern: str,
    replacement: str,
) -> None:
    """PyPI provenance must cover each locked artifact URL, hash, and size.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        pattern: First artifact metadata pattern to contaminate.
        replacement: Invalid metadata text to insert.

    """
    lock = committed_sdk_repository.package / "uv.lock"
    original = lock.read_text(encoding="utf-8")
    contaminated_text, replacements = re.subn(
        pattern,
        replacement,
        original,
        count=1,
    )
    assert replacements == 1
    lock.write_text(contaminated_text, encoding="utf-8")
    contaminated = committed_sdk_repository.commit_all("corrupt lock artifact")

    with pytest.raises(PublicAuditError, match="artifact"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )


def test_extraction_rejects_uv_source_override(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """A source override must fail even when declared requirements look public.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    pyproject = committed_sdk_repository.package / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8")
        + '\n[tool.uv.sources]\nhttpx = { path = "../private-httpx" }\n',
        encoding="utf-8",
    )
    contaminated = committed_sdk_repository.commit_all("add private uv source")

    with pytest.raises(PublicAuditError, match="source override"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )


@pytest.mark.parametrize(
    ("relative_path", "content"),
    [
        ("pyproject.toml", "[project]\nname = 1\n"),
        ("uv.lock", 'version = 1\npackage = "invalid"\n'),
    ],
)
def test_extraction_rejects_malformed_dependency_metadata_safely(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    relative_path: str,
    content: str,
) -> None:
    """Malformed public metadata must become a typed failure, never a traceback.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        relative_path: Dependency metadata path to corrupt.
        content: Syntactically valid but structurally invalid TOML.

    """
    path = committed_sdk_repository.package / relative_path
    path.write_text(content, encoding="utf-8")
    contaminated = committed_sdk_repository.commit_all("corrupt dependency metadata")

    with pytest.raises(PublicAuditError, match="dependency metadata"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )

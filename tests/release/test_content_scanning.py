"""Sensitive-content and private-import public extraction tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parampilot_release.errors import PublicAuditError
from parampilot_release.extraction import extract_public_tree
from tests.release.support import CommittedSdkRepository


def _approve_extra_path(
    repository: CommittedSdkRepository,
    relative_path: str,
    content: str,
) -> None:
    """Add one fixture file to the exact reviewed source allowlist.

    Args:
        repository: Mutable committed-SDK fixture.
        relative_path: New package-relative file path.
        content: UTF-8 source content for the new file.

    Returns:
        None.

    """
    repository.package.joinpath(relative_path).write_text(content, encoding="utf-8")
    allowlist = repository.package / "contracts" / "public-source-allowlist.txt"
    lines = allowlist.read_text(encoding="utf-8").splitlines()
    comments = [line for line in lines if line.startswith("#")]
    entries = [line for line in lines if line and not line.startswith("#")]
    allowlist.write_text(
        "\n".join([*comments, *sorted([*entries, relative_path]), ""]),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("relative_path", "content", "expected"),
    [
        (
            "README.md",
            "owa_" + "pat-" + "abcdefghijklmnopqrstuvwxyz0123456789\n",
            "credential",
        ),
        ("README.md", "pypi-" + "A" * 64 + "\n", "credential"),
        ("README.md", "github_" + "pat_" + "A" * 80 + "\n", "credential"),
        (
            "README.md",
            "/".join(("", "root", "private-parampilot", "source.py")) + "\n",
            "absolute path",
        ),
        (
            "README.md",
            "internal endpoint " + ".".join(("10", "42", "1", "7")) + "\n",
            "network address",
        ),
        ("examples/__init__.py", "import parampilot_backend\n", "private import"),
        (
            "examples/__init__.py",
            'from importlib import import_module as load\nload("parampilot_backend")\n',
            "private import",
        ),
        (
            "examples/__init__.py",
            '__import__(name="parampilot_backend")\n',
            "private import",
        ),
        (
            "examples/__init__.py",
            'import importlib as loader\nloader.import_module("parampilot_backend")\n',
            "private import",
        ),
        (
            "examples/__init__.py",
            'from builtins import __import__ as load\nload("parampilot_backend")\n',
            "private import",
        ),
        (
            "examples/__init__.py",
            'import builtins as runtime\nruntime.__import__("parampilot_backend")\n',
            "private import",
        ),
    ],
)
def test_extraction_rejects_sensitive_content_and_private_imports(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    relative_path: str,
    content: str,
    expected: str,
) -> None:
    """Credential-shaped text and private imports must never cross the boundary.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        relative_path: Package-relative file to contaminate.
        content: Unsafe public source content.
        expected: Expected audit diagnostic fragment.

    """
    path = committed_sdk_repository.package / relative_path
    path.write_text(content, encoding="utf-8")
    contaminated = committed_sdk_repository.commit_all("add unsafe public content")

    with pytest.raises(PublicAuditError, match=expected):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )


def test_extraction_rejects_owner_denied_private_hostname(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Deployment-specific private text must be injectable into the deny scan.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    readme = committed_sdk_repository.package / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "private-control.example\n",
        encoding="utf-8",
    )
    contaminated = committed_sdk_repository.commit_all("add private hostname")

    with pytest.raises(PublicAuditError, match="owner-denied"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
            denied_literals=("private-control.example",),
        )


def test_extraction_rejects_sensitive_allowlisted_filename_without_echoing_it(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Credential-shaped public filenames must fail with a redacted diagnostic.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    credential = "owa_" + "pat-" + "abcdefghijklmnopqrstuvwxyz0123456789"
    relative_path = f"docs/{credential}.md"
    _approve_extra_path(
        committed_sdk_repository,
        relative_path,
        "safe content\n",
    )
    contaminated = committed_sdk_repository.commit_all("add sensitive filename")

    with pytest.raises(PublicAuditError, match="credential") as failure:
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )

    assert credential not in str(failure.value)


def test_extraction_rejects_owner_denied_allowlisted_filename(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Owner-denied text in a filename must stop the public extraction.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    denied = "private-control.example"
    relative_path = f"docs/{denied}.md"
    _approve_extra_path(
        committed_sdk_repository,
        relative_path,
        "safe content\n",
    )
    contaminated = committed_sdk_repository.commit_all("add denied filename")

    with pytest.raises(PublicAuditError, match="owner-denied") as failure:
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
            denied_literals=(denied,),
        )

    assert denied not in str(failure.value)


def test_extraction_rejects_non_utf8_allowlisted_source(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
) -> None:
    """Every initial public source file must be inspectable UTF-8 text.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.

    """
    marker = committed_sdk_repository.package / "src" / "parampilot" / "py.typed"
    marker.write_bytes(b"\xff\xfe")
    contaminated = committed_sdk_repository.commit_all("corrupt type marker")

    with pytest.raises(PublicAuditError, match="UTF-8"):
        extract_public_tree(
            repository_root=contaminated.root,
            output_root=tmp_path / "public",
            expected_commit=contaminated.commit,
        )


def test_public_openapi_contains_no_embedded_example_values() -> None:
    """Generated public contracts must not carry unreviewed example payloads."""
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "programmatic-openapi.json"
        ).read_text(encoding="utf-8")
    )

    assert _embedded_example_paths(schema) == []


def _embedded_example_paths(value: object) -> list[str]:
    """Return JSON paths whose keys embed OpenAPI example values.

    Args:
        value: Decoded public OpenAPI document or nested JSON value.

    Returns:
        Sorted paths ending in ``example`` or ``examples`` keys.

    """
    pending: list[tuple[str, object]] = [("$", value)]
    found: list[str] = []
    while pending:
        path, current = pending.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                child_path = f"{path}.{key}"
                if key in {"example", "examples"}:
                    found.append(child_path)
                pending.append((child_path, child))
        elif isinstance(current, list):
            pending.extend(
                (f"{path}[{index}]", child) for index, child in enumerate(current)
            )
    return sorted(found)

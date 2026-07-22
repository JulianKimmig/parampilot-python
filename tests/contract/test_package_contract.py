"""Behavioral packaging and source-isolation tests for the public SDK."""

from __future__ import annotations

import ast
import importlib.metadata
import re
import sys
from collections.abc import Iterator
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PACKAGE_ROOT / "src" / "parampilot"
PUBLIC_SOURCE_ROOTS = (
    SOURCE_ROOT,
    PACKAGE_ROOT / "parampilot_codegen",
    PACKAGE_ROOT / "parampilot_release",
)
HANDWRITTEN_SOURCE_ROOTS = (
    *PUBLIC_SOURCE_ROOTS,
    PACKAGE_ROOT / "examples",
    PACKAGE_ROOT / "tests",
)
FORBIDDEN_IMPORT_ROOTS = {
    "bofire",
    "django",
    "parampilot_backend",
    "parampilot_worker",
}
ABSOLUTE_WORKSPACE_PATHS = (
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\"),
)


def _project_metadata() -> dict[str, object]:
    """Load the package's PEP 621 metadata.

    Returns:
        The parsed ``project`` table from ``pyproject.toml``.

    """
    document = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())
    return document["project"]


def _public_python_paths() -> Iterator[Path]:
    """Iterate over public runtime and development Python source.

    Yields:
        One Python source path at a time.

    """
    for source_root in PUBLIC_SOURCE_ROOTS:
        yield from source_root.rglob("*.py")


def _handwritten_python_paths() -> Iterator[Path]:
    """Iterate over every shipped handwritten Python source, example, and test.

    Yields:
        One handwritten Python source path at a time.

    """
    for source_root in HANDWRITTEN_SOURCE_ROOTS:
        yield from source_root.rglob("*.py")


def test_public_metadata_uses_the_approved_identity_and_dependencies() -> None:
    """The distribution must freeze the approved public identity and runtime set."""
    project = _project_metadata()

    assert project["name"] == "parampilot"
    assert project["requires-python"] == ">=3.10,<3.15"
    assert project["license"] == "Apache-2.0"
    assert project["authors"] == [{"name": "Julian Kimmig"}]
    assert project["dependencies"] == [
        "httpx>=0.28.1,<1",
        "pydantic>=2.12,<3",
    ]
    assert project["urls"]["Source"] == (
        "https://github.com/JulianKimmig/parampilot-python"
    )


def test_package_metadata_has_no_private_or_local_dependency() -> None:
    """No dependency group may make the public artifact depend on private source."""
    metadata_text = (PACKAGE_ROOT / "pyproject.toml").read_text().lower()
    forbidden_fragments = (
        "parampilot-backend",
        "parampilot_backend",
        "parampilot-worker",
        "parampilot_worker",
        "django",
        "bofire",
        "file:",
        "git+",
        "../",
        "/home/",
    )

    assert not [item for item in forbidden_fragments if item in metadata_text]


def test_build_configuration_packages_only_the_public_import_root() -> None:
    """The wheel target must use an explicit allowlist for the public package."""
    document = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())

    assert document["build-system"]["build-backend"] == "hatchling.build"
    assert document["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/parampilot"
    ]


def test_license_notice_and_typing_marker_are_present() -> None:
    """Published wheels must carry licensing, ownership, and PEP 561 metadata."""
    license_text = (PACKAGE_ROOT / "LICENSE").read_text()
    notice_text = (PACKAGE_ROOT / "NOTICE").read_text()

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "Copyright 2026 Julian Kimmig" in notice_text
    assert (SOURCE_ROOT / "py.typed").is_file()


def test_public_import_exposes_clients_downloads_metadata_and_errors() -> None:
    """The stable import root must expose primary SDK interaction types."""
    from parampilot import (
        ApiResponse,
        AskJobHandle,
        AsyncDownload,
        AsyncParamPilot,
        Download,
        JobAuthenticationError,
        JobCompatibilityError,
        JobWaitTimeoutError,
        ParamPilot,
        PredictJobHandle,
        TrainingJobHandle,
        TrainingRequiredError,
    )

    assert AsyncParamPilot.__name__ == "AsyncParamPilot"
    assert ParamPilot.__name__ == "ParamPilot"
    assert AsyncDownload.__name__ == "AsyncDownload"
    assert Download.__name__ == "Download"
    assert AskJobHandle.__name__ == "AskJobHandle"
    assert PredictJobHandle.__name__ == "PredictJobHandle"
    assert TrainingJobHandle.__name__ == "TrainingJobHandle"
    assert JobAuthenticationError.__name__ == "JobAuthenticationError"
    assert JobCompatibilityError.__name__ == "JobCompatibilityError"
    assert JobWaitTimeoutError.__name__ == "JobWaitTimeoutError"
    assert ApiResponse.__name__ == "ApiResponse"
    assert TrainingRequiredError.__name__ == "TrainingRequiredError"
    assert importlib.metadata.version("parampilot")


def test_public_source_has_no_private_import_or_absolute_workspace_path() -> None:
    """Public Python source must remain independent of proprietary package paths."""
    private_imports: list[str] = []
    leaked_paths: list[Path] = []
    for path in _public_python_paths():
        source = path.read_text()
        if any(pattern.search(source) for pattern in ABSOLUTE_WORKSPACE_PATHS):
            leaked_paths.append(path)
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                private_imports.extend(
                    alias.name
                    for alias in node.names
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORT_ROOTS
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                    private_imports.append(node.module)

    assert private_imports == []
    assert leaked_paths == []


def test_handwritten_source_is_documented_and_below_the_module_limit() -> None:
    """Every handwritten module and callable must be documented and stay modular."""
    undocumented: list[str] = []
    oversized: list[str] = []
    for path in _handwritten_python_paths():
        if "generated" in path.parts:
            continue
        source = path.read_text()
        if len(source.splitlines()) > 300:
            oversized.append(str(path.relative_to(PACKAGE_ROOT)))
        tree = ast.parse(source, filename=str(path))
        if ast.get_docstring(tree) is None:
            undocumented.append(str(path.relative_to(PACKAGE_ROOT)))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if ast.get_docstring(node) is None:
                    undocumented.append(
                        f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}:{node.name}"
                    )

    assert oversized == []
    assert undocumented == []


def test_import_does_not_gain_private_modules_from_the_repository() -> None:
    """Importing the SDK must not load a private runtime transitively."""
    private_before = {
        name for name in sys.modules if name.split(".")[0] in FORBIDDEN_IMPORT_ROOTS
    }

    __import__("parampilot")

    private_after = {
        name for name in sys.modules if name.split(".")[0] in FORBIDDEN_IMPORT_ROOTS
    }
    assert private_after == private_before

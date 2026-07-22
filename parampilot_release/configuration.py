"""Reviewed public-tree allowlist and release manifest constants."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from parampilot_release.errors import PublicAuditError

ALLOWLIST_VERSION = 1
MANIFEST_NAME = ".parampilot-public-manifest.json"
PRIVATE_PACKAGE_PATH = PurePosixPath("packages/parampilot-api")
PUBLIC_SOURCE_ALLOWLIST = PurePosixPath("contracts/public-source-allowlist.txt")
SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
WINDOWS_RESERVED_PATH_NAMES = frozenset(
    {
        "AUX",
        "CON",
        "NUL",
        "PRN",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
REQUIRED_PUBLIC_PATHS = frozenset(
    {
        ".github/workflows/ci.yml",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "NOTICE",
        "README.md",
        "SECURITY.md",
        "contracts/operation-coverage.json",
        "contracts/programmatic-openapi.json",
        PUBLIC_SOURCE_ALLOWLIST.as_posix(),
        "contracts/release-compatibility.json",
        "contracts/runtime-dependency-review.json",
        "docs/quickstart.md",
        "docs/release-and-compatibility.md",
        "docs/workflows-and-recovery.md",
        "parampilot_codegen/__main__.py",
        "parampilot_release/__main__.py",
        "pyproject.toml",
        "pytest.toml",
        "src/parampilot/py.typed",
        "tests/contract/test_distribution_artifacts.py",
        "tests/contract/test_generation_pipeline.py",
        "tests/contract/test_package_contract.py",
        "tests/examples/test_documentation_safety.py",
        "tests/examples/test_explicit_workflow_examples.py",
        "tests/release/clean_wheel_probe.py",
        "tests/release/conftest.py",
        "tests/release/support.py",
        "tests/release/test_allowlist_validation.py",
        "tests/release/test_content_scanning.py",
        "tests/release/test_dependency_scanning.py",
        "tests/release/test_public_audit.py",
        "tests/release/test_public_extraction.py",
        "tests/release/test_release_cli.py",
        "tests/release/test_release_metadata.py",
        "uv.lock",
    }
)


def load_public_source_allowlist(root: Path) -> tuple[PurePosixPath, ...]:
    """Load and validate the exact reviewed public source file list.

    Args:
        root: Candidate package or extracted public tree root.

    Returns:
        Sorted normalized package-relative public source paths.

    Raises:
        PublicAuditError: If the list is absent, malformed, incomplete, or unsafe.

    """
    path = root.joinpath(*PUBLIC_SOURCE_ALLOWLIST.parts)
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise PublicAuditError(
            "public source allowlist is missing or invalid"
        ) from error
    values: list[str] = []
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if raw_line != line:
            raise PublicAuditError("public source allowlist paths must be normalized")
        values.append(line)
    if not values or values != sorted(values) or len(values) != len(set(values)):
        raise PublicAuditError(
            "public source allowlist must be non-empty, sorted, and unique"
        )
    unsafe = any(not is_safe_public_path(value) for value in values)
    if unsafe:
        raise PublicAuditError("public source allowlist contains an unsafe path")
    normalized = tuple(PurePosixPath(value) for value in values)
    if PUBLIC_SOURCE_ALLOWLIST not in normalized:
        raise PublicAuditError("public source allowlist must include itself")
    missing = sorted(REQUIRED_PUBLIC_PATHS - set(values))
    if missing:
        raise PublicAuditError(
            f"required public allowlist path is missing: {missing[0]}"
        )
    return normalized


def is_safe_public_path(value: str) -> bool:
    """Return whether one public path is normalized and cross-platform safe.

    Args:
        value: Candidate package-relative POSIX path.

    Returns:
        Whether the path is root-confined and uses portable components.

    """
    path = PurePosixPath(value)
    components = path.parts
    return (
        bool(value)
        and bool(components)
        and not path.is_absolute()
        and not any(component in {".", ".."} for component in components)
        and path.as_posix() == value
        and all(
            SAFE_PATH_COMPONENT.fullmatch(component) is not None
            and not component.endswith(".")
            and component.split(".", 1)[0].upper() not in WINDOWS_RESERVED_PATH_NAMES
            for component in components
        )
    )


__all__ = [
    "ALLOWLIST_VERSION",
    "MANIFEST_NAME",
    "PRIVATE_PACKAGE_PATH",
    "PUBLIC_SOURCE_ALLOWLIST",
    "REQUIRED_PUBLIC_PATHS",
    "is_safe_public_path",
    "load_public_source_allowlist",
]

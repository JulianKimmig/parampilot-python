"""Archive-level isolation tests for the public SDK wheel and source distribution."""

from __future__ import annotations

import email
import hashlib
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

import pytest

from parampilot_release.scanning import scan_sensitive_text

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SOURCE_ALLOWLIST = PACKAGE_ROOT / "contracts" / "public-source-allowlist.txt"
FORBIDDEN_TEXT = (
    "/home/",
    "C:\\",
    "parampilot_backend",
    "parampilot_worker",
    "Requires-Dist: Django",
    "Requires-Dist: bofire",
)


@pytest.fixture(scope="session")
def built_artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build wheel and sdist into a clean session-temporary directory.

    Args:
        tmp_path_factory: Pytest's session-scoped temporary-directory factory.

    Returns:
        Directory containing freshly built public distribution artifacts.

    """
    output = tmp_path_factory.mktemp("parampilot-distributions")
    subprocess.run(
        ["uv", "build", "--no-build-isolation", "--out-dir", str(output)],
        cwd=PACKAGE_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _single_artifact(artifact_root: Path, pattern: str) -> Path:
    """Return the single built artifact matching ``pattern``.

    Args:
        artifact_root: Directory containing freshly built artifacts.
        pattern: Filename glob evaluated inside ``artifact_root``.

    Returns:
        The one matching artifact path.

    """
    matches = sorted(artifact_root.glob(pattern))
    assert len(matches) == 1, f"expected one {pattern} artifact, found {matches}"
    return matches[0]


def _public_source_allowlist() -> set[str]:
    """Load the exact reviewed source paths allowed in a public sdist.

    Returns:
        Normalized package-relative paths from the committed allowlist.

    """
    return {
        line
        for raw_line in PUBLIC_SOURCE_ALLOWLIST.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    }


def test_repeated_builds_are_byte_reproducible(
    built_artifacts: Path,
    tmp_path: Path,
) -> None:
    """Two builds from one source tree must produce byte-identical archives.

    Args:
        built_artifacts: First fresh wheel and sdist directory.
        tmp_path: Pytest-managed second build directory.

    """
    second = tmp_path / "second-build"
    subprocess.run(
        ["uv", "build", "--no-build-isolation", "--out-dir", str(second)],
        cwd=PACKAGE_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    for pattern in ("*.whl", "*.tar.gz"):
        first_path = _single_artifact(built_artifacts, pattern)
        second_path = _single_artifact(second, pattern)
        assert (
            hashlib.sha256(first_path.read_bytes()).digest()
            == hashlib.sha256(second_path.read_bytes()).digest()
        )


def test_wheel_contains_only_the_public_package_and_distribution_metadata(
    built_artifacts: Path,
) -> None:
    """The wheel must include typed public code and no monorepo-owned package.

    Args:
        built_artifacts: Fresh wheel and sdist directory.

    """
    wheel = _single_artifact(built_artifacts, "*.whl")

    with zipfile.ZipFile(wheel) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        for member in members:
            if not member.is_dir():
                scan_sensitive_text(archive.read(member).decode("utf-8"))
        roots = {name.split("/", 1)[0] for name in names}
        metadata_name = next(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        metadata = email.message_from_bytes(archive.read(metadata_name))
        python_text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in names
            if name.endswith((".json", ".py", ".pyi", ".txt"))
        )

    assert len(names) == len(set(names))
    assert not [
        member.filename
        for member in members
        if stat.S_ISLNK(member.external_attr >> 16)
    ]
    assert all(
        not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts
        for name in names
    )
    assert "parampilot" in roots
    assert all(root == "parampilot" or root.endswith(".dist-info") for root in roots)
    assert "parampilot/py.typed" in names
    assert "parampilot/generated/models.py" in names
    assert "parampilot/generated/model_exports.py" in names
    assert "parampilot/generated/operations.json" in names
    assert "parampilot/generated/provenance.json" in names
    assert "parampilot/models/__init__.pyi" in names
    assert any(name.endswith(".dist-info/licenses/LICENSE") for name in names)
    assert any(name.endswith(".dist-info/licenses/NOTICE") for name in names)
    assert metadata["Name"] == "parampilot"
    assert metadata["License-Expression"] == "Apache-2.0"
    assert metadata.get_all("Requires-Dist") == [
        "httpx<1,>=0.28.1",
        "pydantic<3,>=2.12",
    ]
    assert not [item for item in FORBIDDEN_TEXT if item in python_text]


def test_sdist_uses_an_explicit_public_source_allowlist(
    built_artifacts: Path,
) -> None:
    """The sdist must contain SDK inputs without sibling private package trees.

    Args:
        built_artifacts: Fresh wheel and sdist directory.

    """
    sdist = _single_artifact(built_artifacts, "*.tar.gz")

    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
        assert members
        assert len({member.name for member in members}) == len(members)
        assert all(member.isdir() or member.isfile() for member in members)
        assert all(
            not PurePosixPath(member.name).is_absolute()
            and ".." not in PurePosixPath(member.name).parts
            for member in members
        )
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        assert len(roots) == 1
        file_members = [member for member in members if member.isfile()]
        for member in file_members:
            extracted = archive.extractfile(member)
            assert extracted is not None
            scan_sensitive_text(extracted.read().decode("utf-8"))
        assert all(len(PurePosixPath(member.name).parts) > 1 for member in file_members)
        normalized = [
            PurePosixPath(*PurePosixPath(member.name).parts[1:]).as_posix()
            for member in file_members
        ]
        metadata_member = next(
            member
            for member in file_members
            if PurePosixPath(*PurePosixPath(member.name).parts[1:]).as_posix()
            == "PKG-INFO"
        )
        package_metadata = archive.extractfile(metadata_member)
        assert package_metadata is not None
        metadata_text = package_metadata.read().decode("utf-8")

    required = {
        ".gitignore",
        ".github/workflows/ci.yml",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "NOTICE",
        "README.md",
        "SECURITY.md",
        "pyproject.toml",
        "pytest.toml",
        "contracts/operation-coverage.json",
        "contracts/programmatic-openapi.json",
        "contracts/public-source-allowlist.txt",
        "contracts/release-compatibility.json",
        "contracts/runtime-dependency-review.json",
        "docs/quickstart.md",
        "docs/release-and-compatibility.md",
        "docs/workflows-and-recovery.md",
        "examples/async_explicit_training_workflow.py",
        "examples/sync_explicit_training_workflow.py",
        "parampilot_codegen/__init__.py",
        "parampilot_codegen/__main__.py",
        "parampilot_release/__init__.py",
        "parampilot_release/__main__.py",
        "src/parampilot/py.typed",
        "src/parampilot/generated/models.py",
        "src/parampilot/generated/operations.json",
        "src/parampilot/generated/provenance.json",
        "tests/contract/test_package_contract.py",
        "tests/release/clean_wheel_probe.py",
        "tests/release/test_public_extraction.py",
        "uv.lock",
    }
    assert required.issubset(normalized)
    assert set(normalized) == _public_source_allowlist() | {"PKG-INFO"}
    assert len(normalized) == len(set(normalized))
    assert not [name for name in normalized if name.startswith("packages/")]
    assert not [name for name in normalized if "parampilot_backend" in name]
    assert not [name for name in normalized if "parampilot_worker" in name]
    assert not [item for item in FORBIDDEN_TEXT if item in metadata_text]

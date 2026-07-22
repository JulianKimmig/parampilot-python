"""Release metadata, compatibility, CI, and no-publication contract tests."""

from __future__ import annotations

import json
import re
import sys
from importlib.metadata import Distribution, distributions
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = PACKAGE_ROOT.parents[1]
SUPPORTED_PYTHONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]


def test_release_documents_and_machine_readable_compatibility_exist() -> None:
    """A public candidate must explain support, security, changes, and recovery."""
    required = (
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "docs/release-and-compatibility.md",
        "contracts/release-compatibility.json",
        "contracts/runtime-dependency-review.json",
    )
    assert not [path for path in required if not (PACKAGE_ROOT / path).is_file()]

    contract = json.loads(
        (PACKAGE_ROOT / "contracts" / "release-compatibility.json").read_text(
            encoding="utf-8"
        )
    )
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]
    provenance = json.loads(
        (
            PACKAGE_ROOT / "src" / "parampilot" / "generated" / "provenance.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["format_version"] == 2
    assert contract["package_version"] == project["version"]
    assert contract["python"] == SUPPORTED_PYTHONS
    assert contract["programmatic_api_major"] == 2
    assert contract["schema_sha256"] == provenance["input"]["sha256"]
    assert contract["runtime_dependencies"] == project["dependencies"]
    assert contract["real_worker_profile"] == {
        "cleanup": "in-memory",
        "credentials": False,
        "data": "four-row-synthetic",
        "network": False,
        "result": "passed",
        "timeout_seconds": 300,
    }
    assert contract["provenance"] == "manifest-only"
    assert contract["release_disposition"] == "candidate-dry-run-only"
    assert contract["external_v1_consumers"] == "none-owner-confirmed"
    assert contract["data_review"] == "owner-approved-no-additional-deny-literals"


def test_runtime_dependency_license_review_matches_locked_transitive_graph() -> None:
    """Every runtime package in the universal lock must have an approved license."""
    lock = tomllib.loads((PACKAGE_ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {package["name"]: package for package in lock["package"]}
    pending = [
        dependency["name"] for dependency in packages["parampilot"]["dependencies"]
    ]
    runtime: dict[str, str] = {}
    while pending:
        name = pending.pop()
        if name in runtime:
            continue
        package = packages[name]
        runtime[name] = package["version"]
        pending.extend(
            dependency["name"] for dependency in package.get("dependencies", [])
        )

    review = json.loads(
        (PACKAGE_ROOT / "contracts" / "runtime-dependency-review.json").read_text(
            encoding="utf-8"
        )
    )
    reviewed = {item["name"]: item for item in review["packages"]}

    assert review["format_version"] == 1
    assert review["decision"] == "approved-for-initial-candidate"
    assert set(reviewed) == set(runtime)
    assert {name: item["version"] for name, item in reviewed.items()} == runtime
    assert all(
        re.fullmatch(r"[A-Za-z0-9-.+]+", item["license"]) for item in reviewed.values()
    )
    assert all(
        item["source"] == f"https://pypi.org/project/{name}/{item['version']}/"
        for name, item in reviewed.items()
    )


def test_runtime_dependency_licenses_match_installed_distribution_metadata() -> None:
    """Each interpreter must confirm its installed runtime license metadata."""
    review = json.loads(
        (PACKAGE_ROOT / "contracts" / "runtime-dependency-review.json").read_text(
            encoding="utf-8"
        )
    )
    reviewed = {item["name"]: item for item in review["packages"]}
    expected = set(reviewed)
    if sys.version_info >= (3, 11):
        expected.remove("exceptiongroup")

    installed = {
        name: distribution
        for distribution in distributions()
        if (name := _canonical_distribution_name(distribution.metadata["Name"]))
        in expected
    }

    assert set(installed) == expected
    for name, distribution in installed.items():
        assert _distribution_license(distribution) == reviewed[name]["license"]


def test_public_ci_covers_python_matrix_and_never_publishes() -> None:
    """Public CI must validate every supported Python without upload authority."""
    workflow = PACKAGE_ROOT / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8")

    _assert_read_only_workflow(text)
    assert all(f'"{version}"' in text for version in SUPPORTED_PYTHONS)
    assert "parampilot_codegen --check" in text
    assert "ruff check" in text
    assert "ruff format --check" in text
    assert "mypy" in text
    assert "pytest" in text
    assert "uv build" in text
    assert "uv audit --locked" in text
    assert "uv venv" in text
    assert "uv pip install --python" in text
    assert "tests/release/clean_wheel_probe.py" in text
    assert "lowest-direct" in text
    assert 'mv uv.lock "${RUNNER_TEMP}/candidate-uv.lock"' in text
    assert 'version("httpx") == "0.28.1"' in text
    assert 'version("pydantic").startswith("2.12.")' in text
    assert _unpinned_actions(text) == []
    assert not _publication_commands(text)


def test_monorepo_ci_enforces_live_backend_to_sdk_drift_when_available() -> None:
    """Private CI must link live schema export to public generated contracts."""
    workflow = MONOREPO_ROOT / ".github" / "workflows" / "parampilot-public-sdk.yml"
    if not (MONOREPO_ROOT / "packages" / "parampilot-backend").is_dir():
        pytest.skip("private monorepo is intentionally absent")
    text = workflow.read_text(encoding="utf-8")

    _assert_read_only_workflow(text)
    assert "export_openapi_schema --audience programmatic --check" in text
    assert "uv run python manage.py test" in text
    assert "uv run --locked --with ../parampilot-api" in text
    assert "tests.test_public_sdk_integration" in text
    assert "--schema-source" in text
    assert "parampilot-backend/schemas/programmatic-openapi.json" in text
    assert "parampilot_codegen --check" in text
    assert "submodules: recursive" in text
    assert "parampilot_release extract" not in text
    assert "parampilot_release audit" not in text
    assert "parampilot-python-public" not in text
    assert "tests/release/clean_wheel_probe.py" not in text
    assert "packages/worker" in text
    assert "uv run pytest" in text
    assert 'python-version: "3.12"' in text
    assert _unpinned_actions(text) == []
    assert not _publication_commands(text)


def test_notice_and_project_metadata_use_owner_approved_identity() -> None:
    """Package ownership, license, repository, and Python range must stay aligned."""
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]
    notice = (PACKAGE_ROOT / "NOTICE").read_text(encoding="utf-8")

    assert project["name"] == "parampilot"
    assert project["license"] == "Apache-2.0"
    assert project["requires-python"] == ">=3.10,<3.15"
    assert project["authors"] == [{"name": "Julian Kimmig"}]
    assert project["urls"]["Source"] == (
        "https://github.com/JulianKimmig/parampilot-python"
    )
    assert "Copyright 2026 Julian Kimmig" in notice


def _canonical_distribution_name(value: str) -> str:
    """Normalize one distribution name for review-file lookup.

    Args:
        value: Distribution name from installed package metadata.

    Returns:
        Lowercase PEP 503-compatible name.

    """
    return re.sub(r"[-_.]+", "-", value).lower()


def _distribution_license(distribution: Distribution) -> str:
    """Return one exact SPDX license from installed distribution metadata.

    Args:
        distribution: Installed runtime distribution under review.

    Returns:
        Declared SPDX expression or the unambiguous classifier mapping.

    Raises:
        AssertionError: If the distribution has no unambiguous license value.

    """
    metadata = distribution.metadata
    declared = metadata.get("License-Expression") or metadata.get("License")
    if declared:
        return declared.strip()
    classifier_licenses = {
        "License :: OSI Approved :: MIT License": "MIT",
    }
    matched = {
        classifier_licenses[classifier]
        for classifier in metadata.get_all("Classifier", [])
        if classifier in classifier_licenses
    }
    if len(matched) != 1:
        raise AssertionError(
            f"runtime distribution has ambiguous license metadata: {distribution.name}"
        )
    return matched.pop()


def _publication_commands(text: str) -> list[str]:
    """Return prohibited upload or repository-mutation snippets in CI text.

    Args:
        text: Workflow source under review.

    Returns:
        Matching publication command fragments.

    """
    forbidden = (
        "gh-action-pypi-publish",
        "twine upload",
        "uv publish",
        "git push",
        "gh release create",
    )
    return [value for value in forbidden if value in text]


def _assert_read_only_workflow(text: str) -> None:
    """Assert that one workflow cannot inherit credentials or write authority.

    Args:
        text: Workflow source under review.

    """
    assert re.search(r"^permissions:\n  contents: read$", text, re.MULTILINE)
    checkout_count = text.count("actions/checkout@")
    assert checkout_count > 0
    assert checkout_count == text.count("persist-credentials: false")
    assert "pull_request_target:" not in text
    assert "id-token:" not in text
    assert "secrets." not in text


def _unpinned_actions(text: str) -> list[str]:
    """Return GitHub Action references that are not immutable commits.

    Args:
        text: Workflow source under review.

    Returns:
        Action references whose revision is not a full SHA-1 commit.

    """
    references = re.findall(r"uses:\s+([^\s#]+)", text)
    commit = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
    return [reference for reference in references if not commit.fullmatch(reference)]

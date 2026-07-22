"""Command-line behavior tests for credential-free release preparation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parampilot_release.cli import main
from tests.release.support import CommittedSdkRepository


def test_cli_extracts_and_reaudits_without_printing_local_paths(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful CLI output must contain safe identity rather than workspace paths.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        capsys: Pytest output capture fixture.

    """
    output = tmp_path / "public"
    status = main(
        [
            "extract",
            "--repository-root",
            str(committed_sdk_repository.root),
            "--source-commit",
            committed_sdk_repository.commit,
            "--output-root",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert status == 0
    assert payload["status"] == "extracted"
    assert payload["source_commit"] == committed_sdk_repository.commit
    assert str(committed_sdk_repository.root) not in captured.out
    assert str(output) not in captured.out

    status = main(["audit", "--public-root", str(output)])
    captured = capsys.readouterr()
    assert status == 0
    assert json.loads(captured.out)["status"] == "audited"


def test_cli_returns_actionable_failure_without_traceback(
    committed_sdk_repository: CommittedSdkRepository,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Expected release-boundary failures must use a stable nonzero exit status.

    Args:
        committed_sdk_repository: Clean actual-Git SDK fixture.
        tmp_path: Pytest-managed scratch directory.
        capsys: Pytest output capture fixture.

    """
    status = main(
        [
            "extract",
            "--repository-root",
            str(committed_sdk_repository.root),
            "--source-commit",
            "0" * 40,
            "--output-root",
            str(tmp_path / "public"),
        ]
    )
    captured = capsys.readouterr()

    assert status == 1
    assert "commit" in captured.out
    assert "Traceback" not in captured.out

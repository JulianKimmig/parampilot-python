"""Credential-free CLI for public extraction and exact tree auditing."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from parampilot_release.audit import audit_public_tree
from parampilot_release.errors import ReleasePreparationError
from parampilot_release.extraction import extract_public_tree


def parser() -> argparse.ArgumentParser:
    """Build the release preparation command parser.

    Returns:
        Configured parser with extraction and audit subcommands.

    """
    value = argparse.ArgumentParser(
        description="Create or audit a history-isolated ParamPilot public tree.",
    )
    subcommands = value.add_subparsers(dest="command", required=True)
    extract = subcommands.add_parser("extract", help="extract one exact private commit")
    extract.add_argument("--repository-root", type=Path, required=True)
    extract.add_argument("--output-root", type=Path, required=True)
    extract.add_argument("--source-commit", required=True)
    extract.add_argument("--deny-literal", action="append", default=[])
    audit = subcommands.add_parser("audit", help="audit an extracted public tree")
    audit.add_argument("--public-root", type=Path, required=True)
    audit.add_argument("--deny-literal", action="append", default=[])
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Run a local release action without pushing, tagging, or publishing.

    Args:
        argv: Optional command arguments excluding the executable name.

    Returns:
        Zero on success and one for an actionable release-boundary failure.

    """
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "extract":
            result = extract_public_tree(
                repository_root=arguments.repository_root,
                output_root=arguments.output_root,
                expected_commit=arguments.source_commit,
                denied_literals=arguments.deny_literal,
            )
            output = {
                "file_count": result.file_count,
                "manifest_sha256": result.manifest_sha256,
                "source_commit": result.source_commit,
                "status": "extracted",
            }
        else:
            report = audit_public_tree(
                arguments.public_root,
                denied_literals=arguments.deny_literal,
            )
            output = {
                "file_count": report.file_count,
                "manifest_sha256": report.manifest_sha256,
                "source_commit": report.source_commit,
                "status": "audited",
            }
    except ReleasePreparationError as error:
        print(str(error))
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


__all__ = ["main", "parser"]

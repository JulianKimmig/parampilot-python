"""Command-line entry point for deterministic ParamPilot contract generation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from parampilot_codegen.generation import ContractGenerationError, run_generation


def _parser() -> argparse.ArgumentParser:
    """Build the public generation command parser.

    Returns:
        Configured argument parser.

    """
    parser = argparse.ArgumentParser(
        description="Generate or verify ParamPilot public SDK contracts.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate temporarily and fail when committed artifacts drift",
    )
    parser.add_argument(
        "--schema-source",
        type=Path,
        help="authoritative OpenAPI handoff to copy before generation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run generation and return a process exit status.

    Args:
        argv: Optional command arguments excluding the executable name.

    Returns:
        Zero on success and one for actionable generation failures.

    """
    arguments = _parser().parse_args(argv)
    try:
        paths = run_generation(
            check=arguments.check,
            schema_source=arguments.schema_source,
        )
    except (ContractGenerationError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    action = "verified" if arguments.check else "generated"
    print(f"Contract artifacts are current ({len(paths)} files {action}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

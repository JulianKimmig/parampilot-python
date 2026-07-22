"""Pure-data results returned by release extraction and audit operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Completed history-isolated extraction identity.

    Args:
        manifest_path: Local path to the generated public manifest.
        manifest_sha256: SHA-256 over the exact manifest bytes.
        source_commit: Exact private source commit represented by the tree.
        file_count: Number of allowlisted public source files.

    """

    manifest_path: Path
    manifest_sha256: str
    source_commit: str
    file_count: int


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Successful exact public-tree audit identity.

    Args:
        manifest_sha256: SHA-256 over the exact manifest bytes.
        source_commit: Exact private source commit represented by the tree.
        file_count: Number of verified allowlisted public source files.

    """

    manifest_sha256: str
    source_commit: str
    file_count: int


__all__ = ["AuditReport", "ExtractionResult"]

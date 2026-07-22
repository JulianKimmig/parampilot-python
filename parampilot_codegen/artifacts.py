"""Byte-stable artifact rendering, hashing, comparison, and publication helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def render_json(value: Any) -> bytes:
    """Serialize a JSON-compatible value using the canonical public format.

    Args:
        value: JSON-compatible value to serialize.

    Returns:
        UTF-8 bytes with sorted keys, two-space indentation, and final newline.

    """
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def load_json_object(path: Path) -> dict[str, Any]:
    """Load and require a top-level JSON object.

    Args:
        path: JSON file to decode.

    Returns:
        Decoded string-keyed object.

    Raises:
        ValueError: If the top-level JSON value is not an object.

    """
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def sha256_bytes(value: bytes) -> str:
    """Calculate a lowercase SHA-256 digest.

    Args:
        value: Exact bytes to hash.

    Returns:
        Hexadecimal SHA-256 digest.

    """
    return hashlib.sha256(value).hexdigest()


def file_metadata(root: Path, relative_path: Path) -> dict[str, int | str]:
    """Build sanitized size and digest metadata for one artifact.

    Args:
        root: Artifact tree root.
        relative_path: Public path relative to ``root``.

    Returns:
        Relative path, byte size, and SHA-256 metadata.

    """
    value = (root / relative_path).read_bytes()
    return {
        "bytes": len(value),
        "path": relative_path.as_posix(),
        "sha256": sha256_bytes(value),
    }


def artifact_differences(
    expected_root: Path,
    actual_root: Path,
    relative_paths: Iterable[Path],
) -> tuple[str, ...]:
    """Compare generated artifacts and return deterministic diagnostics.

    Args:
        expected_root: Root containing freshly generated expected bytes.
        actual_root: Root containing committed artifact bytes.
        relative_paths: Relative artifact paths to compare in order.

    Returns:
        Empty tuple when current, otherwise one diagnostic per stale path.

    """
    differences: list[str] = []
    for relative_path in relative_paths:
        expected = expected_root / relative_path
        actual = actual_root / relative_path
        if not actual.is_file():
            differences.append(
                f"missing generated artifact: {relative_path.as_posix()}"
            )
        elif expected.read_bytes() != actual.read_bytes():
            differences.append(
                f"changed generated artifact: {relative_path.as_posix()}"
            )
    return tuple(differences)


def publish_artifacts(
    source_root: Path,
    destination_root: Path,
    relative_paths: Iterable[Path],
) -> None:
    """Copy approved generated artifacts into the package tree.

    Args:
        source_root: Complete temporary generated tree.
        destination_root: Public package source root.
        relative_paths: Relative files to publish.

    """
    for relative_path in relative_paths:
        source = source_root / relative_path
        destination = destination_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

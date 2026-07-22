"""Deterministic byte hashing and JSON rendering for release manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest for bytes.

    Args:
        value: Exact bytes to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    """
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for one file.

    Args:
        path: File to hash exactly.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    """
    return sha256_bytes(path.read_bytes())


def render_json(value: Any) -> bytes:
    """Render deterministic indented UTF-8 JSON with one trailing newline.

    Args:
        value: JSON-compatible value.

    Returns:
        Deterministic UTF-8 bytes.

    """
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()


__all__ = ["render_json", "sha256_bytes", "sha256_file"]

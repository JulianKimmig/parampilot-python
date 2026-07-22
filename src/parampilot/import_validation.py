"""Bounded experiment-file validation shared by sync and async resources."""

from __future__ import annotations

from pathlib import PurePath

from parampilot.errors import ConfigurationError

IMPORT_LIMIT = 10 * 1024 * 1024
IMPORT_MEDIA_TYPES = frozenset(
    {
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)


def validated_import_file(
    data: bytes,
    *,
    filename: str,
    content_type: str,
) -> tuple[str, bytes, str]:
    """Validate a bounded byte-backed experiment import.

    Args:
        data: Complete caller-provided file bytes.
        filename: Basename including ``.csv`` or ``.xlsx``.
        content_type: Declared supported media type.

    Returns:
        Validated filename, original bytes, and content type.

    Raises:
        ConfigurationError: If local file metadata or size is unsafe.

    """
    if len(data) > IMPORT_LIMIT:
        raise ConfigurationError("experiment import exceeds the 10 MiB limit")
    if not filename or PurePath(filename).name != filename:
        raise ConfigurationError("filename must be a nonempty basename")
    if content_type not in IMPORT_MEDIA_TYPES:
        raise ConfigurationError("content_type must declare CSV or XLSX")
    return filename, data, content_type

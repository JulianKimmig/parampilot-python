"""Safe binary-response metadata parsing shared by both download handles."""

from __future__ import annotations

from email.message import Message
from pathlib import Path

import httpx


def response_filename(response: httpx.Response) -> str | None:
    """Extract a basename-only attachment filename.

    Args:
        response: Streaming HTTPX response.

    Returns:
        Safe basename or ``None`` when undeclared.

    """
    content_disposition = response.headers.get("Content-Disposition")
    if not content_disposition:
        return None
    message = Message()
    message["content-disposition"] = content_disposition
    candidate = message.get_filename()
    if not candidate:
        return None
    basename = Path(candidate.replace("\\", "/")).name
    return basename or None


def response_content_length(response: httpx.Response) -> int | None:
    """Parse an optional nonnegative response length.

    Args:
        response: Streaming HTTPX response.

    Returns:
        Declared byte count or ``None``.

    """
    value = response.headers.get("Content-Length")
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None

"""Credential-safe request-header assembly shared by both native transports."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from parampilot.configuration import ClientConfiguration
from parampilot.errors import ConfigurationError
from parampilot.operations import Operation
from parampilot.serialization import idempotency_key, required_header

FORBIDDEN_CALLER_HEADERS = frozenset({"authorization", "host", "user-agent"})


def request_headers(
    configuration: ClientConfiguration,
    operation: Operation | None,
    values: Mapping[str, str] | None,
    *,
    accept: str,
) -> dict[str, str]:
    """Build one credential-safe header set reused across retries.

    Args:
        configuration: Validated client authentication configuration.
        operation: Generated operation metadata when available.
        values: Caller/resource headers.
        accept: Requested response media type.

    Returns:
        Complete authenticated request headers.

    Raises:
        ConfigurationError: If callers try to override protected headers.

    """
    headers = configuration.request_headers(accept=accept)
    headers["X-Request-ID"] = str(uuid4())
    for name, value in (values or {}).items():
        if name.lower() in FORBIDDEN_CALLER_HEADERS:
            raise ConfigurationError(f"Caller header {name!r} is managed by the SDK")
        headers[name] = required_header(value, label=name)
    if operation is not None and operation.key_required:
        headers["Idempotency-Key"] = idempotency_key(headers.get("Idempotency-Key"))
    return headers

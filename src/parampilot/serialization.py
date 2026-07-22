"""Transport-neutral request serialization and public identifier validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from parampilot.errors import ConfigurationError

IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
QueryScalar = str | int | float | bool | None


def public_id(value: UUID | str, *, label: str) -> str:
    """Validate and normalize a public UUID accepted by a resource method.

    Args:
        value: UUID object or canonical textual UUID.
        label: Parameter name for diagnostics.

    Returns:
        Canonical lowercase UUID text.

    Raises:
        ConfigurationError: If ``value`` is not a UUID.

    """
    try:
        return str(UUID(str(value)))
    except ValueError as error:
        raise ConfigurationError(f"{label} must be a public UUID") from error


def idempotency_key(value: str | None) -> str:
    """Validate a caller key or generate one stable request key.

    Args:
        value: Optional caller-supplied idempotency key.

    Returns:
        Valid key suitable for one logical mutation and all its retries.

    Raises:
        ConfigurationError: If a supplied key violates the public contract.

    """
    key = value if value is not None else f"sdk-{uuid4().hex}"
    if IDEMPOTENCY_KEY.fullmatch(key) is None:
        raise ConfigurationError(
            "idempotency_key must be 8-128 ASCII characters using "
            "letters, digits, '.', '_', ':', or '-'"
        )
    return key


def required_header(value: str, *, label: str) -> str:
    """Require a nonempty single-line caller header value.

    Args:
        value: Header value candidate.
        label: Public parameter name for diagnostics.

    Returns:
        Validated unchanged header value.

    Raises:
        ConfigurationError: If empty or unsafe for an HTTP header.

    """
    if not value or "\r" in value or "\n" in value:
        raise ConfigurationError(f"{label} must be a nonempty single-line value")
    return value


def page_limit(value: int) -> int:
    """Require the public cursor-page size bound.

    Args:
        value: Page-size candidate.

    Returns:
        Validated integer from 1 through 500.

    Raises:
        ConfigurationError: If the value is boolean, noninteger, or out of range.

    """
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 500:
        raise ConfigurationError("limit must be an integer from 1 to 500")
    return value


def json_value(value: Any) -> Any:
    """Convert typed request data into JSON-compatible wire values.

    Args:
        value: Pydantic model or nested typed JSON value.

    Returns:
        JSON-compatible value using aliases and caller-supplied fields only.

    Raises:
        ConfigurationError: If an unsupported object reaches serialization.

    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ConfigurationError("JSON object keys must be strings")
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [json_value(item) for item in value]
    raise ConfigurationError(f"Unsupported JSON request value: {type(value).__name__}")


def _query_value(value: Any) -> str:
    """Convert one scalar query value to its public wire representation.

    Args:
        value: Scalar query value.

    Returns:
        String suitable for HTTPX query encoding.

    Raises:
        ConfigurationError: If the value is unsupported.

    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (UUID, date, datetime)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    if isinstance(value, (float, int, str)):
        return str(value)
    raise ConfigurationError(f"Unsupported query value: {type(value).__name__}")


def query_items(values: Mapping[str, Any] | None) -> list[tuple[str, QueryScalar]]:
    """Serialize query values with repeated keys for sequences.

    Args:
        values: Optional query mapping; ``None`` values are omitted.

    Returns:
        Ordered HTTPX-compatible query item pairs.

    """
    result: list[tuple[str, QueryScalar]] = []
    for key, value in (values or {}).items():
        if value is None:
            continue
        if isinstance(value, Sequence) and not isinstance(
            value, (bytes, bytearray, str)
        ):
            result.extend((key, _query_value(item)) for item in value)
        else:
            result.append((key, _query_value(value)))
    return result

"""Runtime access to deterministic generated OpenAPI operation metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal
from urllib.parse import quote

from parampilot.errors import ConfigurationError

RetryClassification = Literal["safe_read", "keyed_mutation", "manual_retry"]
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class Operation:
    """Stable request metadata for one public API operation.

    Args:
        operation_id: Stable lower-camel OpenAPI operation identifier.
        method: Uppercase HTTP method.
        path_template: Rooted public API path with named placeholders.
        retry_classification: Conservative automatic retry class.
        key_required: Whether the request requires ``Idempotency-Key``.

    """

    operation_id: str
    method: str
    path_template: str
    retry_classification: RetryClassification
    key_required: bool

    @property
    def automatically_retryable(self) -> bool:
        """Return whether transport-level automatic retry is allowed.

        Returns:
            ``True`` for safe reads and keyed mutations.

        """
        return self.retry_classification in {"safe_read", "keyed_mutation"}

    def path(self, **values: object) -> str:
        """Render and percent-encode every path placeholder exactly once.

        Args:
            **values: Public identifiers keyed by placeholder name.

        Returns:
            Rooted rendered API path.

        Raises:
            ConfigurationError: If values are missing, extra, or empty.

        """
        required = set(PLACEHOLDER.findall(self.path_template))
        supplied = set(values)
        if required != supplied:
            raise ConfigurationError(
                f"Path values for {self.operation_id} must be {sorted(required)}"
            )
        rendered = self.path_template
        for name in sorted(required):
            value = str(values[name])
            if not value:
                raise ConfigurationError(f"Path value {name} must not be empty")
            rendered = rendered.replace(f"{{{name}}}", quote(value, safe=""))
        return rendered


def _object(value: Any, label: str) -> dict[str, Any]:
    """Require a decoded JSON object.

    Args:
        value: Candidate JSON value.
        label: Diagnostic location.

    Returns:
        Validated object.

    Raises:
        RuntimeError: If generated metadata is malformed.

    """
    if not isinstance(value, dict):
        raise RuntimeError(f"Generated operation metadata {label} must be an object")
    return value


@lru_cache(maxsize=1)
def operation_registry() -> dict[str, Operation]:
    """Load and validate the installed generated operation registry once.

    Returns:
        Operation-ID keyed immutable-value registry.

    Raises:
        RuntimeError: If installed generated metadata is malformed.

    """
    resource = files("parampilot.generated").joinpath("operations.json")
    document = _object(json.loads(resource.read_text()), "root")
    values = document.get("operations")
    if document.get("format_version") != 1 or not isinstance(values, list):
        raise RuntimeError("Unsupported generated operation metadata format")
    registry: dict[str, Operation] = {}
    for raw in values:
        item = _object(raw, "entry")
        idempotency = _object(item.get("idempotency"), "idempotency")
        classification = idempotency.get("classification")
        if classification not in {"safe_read", "keyed_mutation", "manual_retry"}:
            raise RuntimeError("Generated retry classification is invalid")
        operation_id = item.get("operation_id")
        method = item.get("method")
        path = item.get("path")
        if (
            not isinstance(operation_id, str)
            or not isinstance(method, str)
            or not isinstance(path, str)
        ):
            raise RuntimeError("Generated operation identity fields are invalid")
        registry[operation_id] = Operation(
            operation_id=operation_id,
            method=method,
            path_template=path,
            retry_classification=classification,
            key_required=bool(idempotency.get("key_required")),
        )
    if len(registry) != len(values):
        raise RuntimeError("Generated operation identifiers must be unique")
    return registry


def operation(operation_id: str) -> Operation:
    """Return one generated public operation.

    Args:
        operation_id: Stable OpenAPI operation identifier.

    Returns:
        Installed operation metadata.

    Raises:
        ConfigurationError: If the operation does not exist.

    """
    try:
        return operation_registry()[operation_id]
    except KeyError as error:
        raise ConfigurationError(
            f"Unknown ParamPilot operation: {operation_id}"
        ) from error

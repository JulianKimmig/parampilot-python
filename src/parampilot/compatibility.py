"""Public API major, capability, and generated-schema compatibility policy."""

from __future__ import annotations

import json
import warnings
from collections.abc import Collection, Mapping
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal

from parampilot.errors import CompatibilityError, SchemaCompatibilityWarning
from parampilot.models import AvailabilityResponse

API_MAJOR = 2
SchemaCompatibility = Literal["warn", "strict", "ignore"]


@lru_cache(maxsize=1)
def expected_schema_digest() -> str:
    """Return the digest of the exact OpenAPI input used for installed models.

    Returns:
        Availability-compatible ``sha256:...`` digest.

    Raises:
        RuntimeError: If installed provenance is malformed.

    """
    resource = files("parampilot.generated").joinpath("provenance.json")
    document = json.loads(resource.read_text())
    try:
        digest = document["input"]["sha256"]
    except (KeyError, TypeError) as error:
        raise RuntimeError("Installed ParamPilot provenance is malformed") from error
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError("Installed ParamPilot schema digest is malformed")
    return f"sha256:{digest}"


def require_api_major(payload: Mapping[str, Any]) -> None:
    """Reject an availability payload from another API major before coercion.

    Args:
        payload: Decoded availability response.

    Raises:
        CompatibilityError: If the semantic version is absent or not v2.

    """
    api_version = payload.get("api_version")
    if not isinstance(api_version, str):
        raise CompatibilityError("Availability response has no valid API version")
    try:
        major = int(api_version.split(".", 1)[0])
    except ValueError as error:
        raise CompatibilityError(
            "Availability response has no valid API major"
        ) from error
    if major != API_MAJOR:
        raise CompatibilityError(
            f"ParamPilot API major {major} is incompatible with SDK major {API_MAJOR}"
        )


def validate_compatibility(
    availability: AvailabilityResponse,
    *,
    required_capabilities: Collection[str],
    schema_compatibility: SchemaCompatibility,
) -> None:
    """Apply capability and same-major schema-digest policy.

    Args:
        availability: Validated v2 availability response.
        required_capabilities: Capabilities required by the caller's feature.
        schema_compatibility: Digest mismatch policy.

    Raises:
        CompatibilityError: For missing capabilities or strict digest drift.

    """
    missing = sorted(set(required_capabilities) - set(availability.capabilities))
    if missing:
        raise CompatibilityError(
            f"ParamPilot server is missing required capabilities: {', '.join(missing)}"
        )
    expected = expected_schema_digest()
    if availability.schema_digest == expected or schema_compatibility == "ignore":
        return
    message = (
        "ParamPilot server schema digest differs from the generated SDK contract "
        f"(server={availability.schema_digest}, sdk={expected})"
    )
    if schema_compatibility == "strict":
        raise CompatibilityError(message)
    warnings.warn(message, SchemaCompatibilityWarning, stacklevel=2)

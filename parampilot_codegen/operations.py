"""Deterministic extraction of typed operation metadata from public OpenAPI."""

from __future__ import annotations

from typing import Any

HTTP_METHODS = frozenset({"delete", "get", "patch", "post", "put"})
COMPONENT_PREFIX = "#/components/schemas/"


def _object(value: Any, label: str) -> dict[str, Any]:
    """Require a string-keyed JSON object.

    Args:
        value: Candidate decoded JSON value.
        label: Human-readable location for failures.

    Returns:
        Validated object.

    Raises:
        ValueError: If ``value`` is not a string-keyed object.

    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"Expected an object for {label}")
    return value


def _array(value: Any, label: str) -> list[Any]:
    """Require a JSON array.

    Args:
        value: Candidate decoded JSON value.
        label: Human-readable location for failures.

    Returns:
        Validated list.

    Raises:
        ValueError: If ``value`` is not a list.

    """
    if not isinstance(value, list):
        raise ValueError(f"Expected an array for {label}")
    return value


def _schema_name(schema: dict[str, Any]) -> str | None:
    """Extract a local component name from a schema reference.

    Args:
        schema: Media-type or parameter schema object.

    Returns:
        Component name for a local reference, otherwise ``None``.

    """
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith(COMPONENT_PREFIX):
        return reference.removeprefix(COMPONENT_PREFIX)
    return None


def _schema_descriptor(value: Any, label: str) -> dict[str, Any]:
    """Preserve an exact schema fragment with its component name when available.

    Args:
        value: Decoded OpenAPI schema fragment.
        label: Human-readable location for failures.

    Returns:
        Stable schema and extracted-name descriptor.

    """
    schema = _object(value, label)
    return {"schema": schema, "schema_name": _schema_name(schema)}


def _content(value: Any, label: str) -> dict[str, dict[str, Any]]:
    """Normalize a media-type map without losing inline schemas.

    Args:
        value: OpenAPI content object.
        label: Human-readable location for failures.

    Returns:
        Sorted media-type descriptors.

    """
    content = _object(value, label)
    result: dict[str, dict[str, Any]] = {}
    for media_type in sorted(content):
        media = _object(content[media_type], f"{label}.{media_type}")
        result[media_type] = _schema_descriptor(
            media["schema"],
            f"{label}.{media_type}.schema",
        )
    return result


def _parameters(values: list[Any], label: str) -> list[dict[str, Any]]:
    """Normalize path, query, and header parameter contracts.

    Args:
        values: Combined path-item and operation parameter values.
        label: Human-readable operation location.

    Returns:
        Parameters sorted by location and name.

    """
    result: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        parameter = _object(value, f"{label}.parameters[{index}]")
        name = parameter["name"]
        location = parameter["in"]
        if not isinstance(name, str) or not isinstance(location, str):
            raise ValueError(f"Expected string parameter name/location for {label}")
        result.append(
            {
                "location": location,
                "name": name,
                "required": bool(parameter.get("required", False)),
                **_schema_descriptor(
                    parameter["schema"],
                    f"{label}.parameters[{index}].schema",
                ),
            }
        )
    return sorted(result, key=lambda item: (item["location"], item["name"]))


def _request_body(operation: dict[str, Any], label: str) -> dict[str, Any] | None:
    """Normalize an optional request body.

    Args:
        operation: OpenAPI operation object.
        label: Human-readable operation location.

    Returns:
        Request body metadata or ``None`` when absent.

    """
    if "requestBody" not in operation:
        return None
    request_body = _object(operation["requestBody"], f"{label}.requestBody")
    return {
        "content": _content(request_body["content"], f"{label}.requestBody.content"),
        "required": bool(request_body.get("required", False)),
    }


def _responses(operation: dict[str, Any], label: str) -> dict[str, Any]:
    """Normalize response media, schemas, and declared headers.

    Args:
        operation: OpenAPI operation object.
        label: Human-readable operation location.

    Returns:
        Status-code keyed response metadata.

    """
    responses = _object(operation["responses"], f"{label}.responses")
    result: dict[str, Any] = {}
    for status in sorted(responses):
        response = _object(responses[status], f"{label}.responses.{status}")
        content = (
            _content(response["content"], f"{label}.responses.{status}.content")
            if "content" in response
            else {}
        )
        headers = (
            sorted(_object(response["headers"], f"{label}.responses.{status}.headers"))
            if "headers" in response
            else []
        )
        result[status] = {
            "content": content,
            "description": response["description"],
            "headers": headers,
        }
    return result


def _auth(operation: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Extract operation-level or root-level security schemes.

    Args:
        operation: OpenAPI operation object.
        root: Full OpenAPI document.

    Returns:
        Authentication requirement and sorted scheme names.

    """
    security_value = (
        operation["security"] if "security" in operation else root.get("security")
    )
    if security_value is None:
        return {"required": False, "schemes": []}
    requirements = _array(security_value, "security")
    schemes = sorted(
        {
            scheme
            for requirement in requirements
            for scheme in _object(requirement, "security requirement")
        }
    )
    return {"required": bool(requirements), "schemes": schemes}


def _idempotency(method: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify retry, idempotency-key, and concurrency requirements.

    Args:
        method: Uppercase HTTP method.
        parameters: Normalized operation parameters.

    Returns:
        Conservative automatic-retry classification and header requirements.

    """
    required_headers = {
        parameter["name"]
        for parameter in parameters
        if parameter["location"] == "header" and parameter["required"]
    }
    all_headers = {
        parameter["name"]
        for parameter in parameters
        if parameter["location"] == "header"
    }
    key_required = "Idempotency-Key" in required_headers
    if method == "GET":
        classification = "safe_read"
    elif key_required:
        classification = "keyed_mutation"
    else:
        classification = "manual_retry"
    return {
        "classification": classification,
        "key_required": key_required,
        "precondition_required": "If-Match" in required_headers,
        "revalidation_supported": "If-None-Match" in all_headers,
    }


def build_operations_document(schema: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic metadata for every public OpenAPI operation.

    Args:
        schema: Complete public OpenAPI document.

    Returns:
        Versioned operation metadata document.

    """
    paths = _object(schema["paths"], "paths")
    operations: list[dict[str, Any]] = []
    for path in sorted(paths):
        path_item = _object(paths[path], f"paths.{path}")
        path_parameters = (
            _array(path_item["parameters"], f"paths.{path}.parameters")
            if "parameters" in path_item
            else []
        )
        for method in sorted(HTTP_METHODS & path_item.keys()):
            operation = _object(path_item[method], f"paths.{path}.{method}")
            operation_parameters = (
                _array(operation["parameters"], f"paths.{path}.{method}.parameters")
                if "parameters" in operation
                else []
            )
            parameters = _parameters(
                [*path_parameters, *operation_parameters],
                f"paths.{path}.{method}",
            )
            operation_id = operation["operationId"]
            if not isinstance(operation_id, str):
                raise ValueError(f"Expected operationId for {method.upper()} {path}")
            operations.append(
                {
                    "auth": _auth(operation, schema),
                    "idempotency": _idempotency(method.upper(), parameters),
                    "method": method.upper(),
                    "operation_id": operation_id,
                    "parameters": parameters,
                    "path": path,
                    "request_body": _request_body(operation, operation_id),
                    "responses": _responses(operation, operation_id),
                    "summary": operation.get("summary"),
                    "tags": sorted(_array(operation["tags"], f"{operation_id}.tags")),
                }
            )
    operations.sort(key=lambda item: item["operation_id"])
    return {"format_version": 1, "operations": operations}

"""Generated runtime and static export surfaces for OpenAPI component models."""

from __future__ import annotations

import keyword
from typing import Any


def component_names(schema: dict[str, Any]) -> tuple[str, ...]:
    """Return validated Python names for all OpenAPI component schemas.

    Args:
        schema: Complete public OpenAPI document.

    Returns:
        Sorted component model names.

    Raises:
        ValueError: If component schemas are absent or not valid identifiers.

    """
    components = schema.get("components")
    if not isinstance(components, dict):
        raise ValueError("OpenAPI components must be an object")
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        raise ValueError("OpenAPI components.schemas must be an object")
    names = tuple(sorted(schemas))
    invalid = [
        name for name in names if not name.isidentifier() or keyword.iskeyword(name)
    ]
    if invalid:
        raise ValueError(f"Component names are not Python identifiers: {invalid}")
    return names


def render_model_exports(names: tuple[str, ...]) -> bytes:
    """Render the runtime allowlist of public generated component names.

    Args:
        names: Sorted public component model names.

    Returns:
        UTF-8 Python module bytes.

    """
    lines = [
        '"""Generated public OpenAPI component export names."""',
        "",
        "from typing import Final",
        "",
        "PUBLIC_MODEL_NAMES: Final[tuple[str, ...]] = (",
    ]
    lines.extend(f'    "{name}",' for name in names)
    lines.extend((")", ""))
    return "\n".join(lines).encode()


def render_model_stub(names: tuple[str, ...]) -> bytes:
    """Render a PEP 561 stub for stable ``parampilot.models`` imports.

    Args:
        names: Sorted public component model names.

    Returns:
        UTF-8 Python stub bytes.

    """
    lines = [
        '"""Generated static exports for public OpenAPI component models."""',
        "",
        "from parampilot.generated.models import (",
    ]
    lines.extend(f"    {name} as {name}," for name in names)
    lines.extend((")", "", "__all__: list[str]", ""))
    return "\n".join(lines).encode()

"""Stable lazy facade for every named public OpenAPI component model."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from parampilot.generated.model_exports import PUBLIC_MODEL_NAMES

__all__ = list(PUBLIC_MODEL_NAMES)


def __getattr__(name: str) -> Any:
    """Resolve one allowlisted generated component model on first access.

    Args:
        name: Requested module attribute.

    Returns:
        Generated model, enum, or root model class.

    Raises:
        AttributeError: If ``name`` is not a public OpenAPI component.

    """
    if name not in PUBLIC_MODEL_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    generated = import_module("parampilot.generated.models")
    value = getattr(generated, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return ordinary module attributes plus generated public model names.

    Returns:
        Sorted introspection names.

    """
    return sorted({*globals(), *PUBLIC_MODEL_NAMES})

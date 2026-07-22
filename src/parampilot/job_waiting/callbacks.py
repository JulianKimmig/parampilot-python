"""Typed callback contracts shared by public job-wait APIs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeAlias

from parampilot.models import PublicModelJobObservation

ProgressCallback: TypeAlias = Callable[[PublicModelJobObservation], None]
AsyncProgressCallback: TypeAlias = Callable[
    [PublicModelJobObservation],
    None | Awaitable[None],
]

__all__ = ["AsyncProgressCallback", "ProgressCallback"]

"""Lazy bounded opaque-cursor iteration shared by async collection resources."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from typing import Protocol, TypeVar

from parampilot.errors import ResponseValidationError

T = TypeVar("T", covariant=True)
P = TypeVar("P", bound="CursorPage[object]")


class CursorPage(Protocol[T]):
    """Structural fields shared by generated public cursor-page models."""

    @property
    def items(self) -> Sequence[T]:
        """Return items in stable server order."""
        ...

    @property
    def next_cursor(self) -> str | None:
        """Return the opaque continuation cursor."""
        ...

    @property
    def has_more(self) -> bool:
        """Return whether another bounded page exists."""
        ...


async def iterate_cursor(
    fetch: Callable[[str | None], Awaitable[CursorPage[T]]],
    *,
    operation_id: str,
) -> AsyncIterator[T]:
    """Lazily traverse cursor pages without rewriting or prefetching.

    Args:
        fetch: Function retrieving exactly one page for an opaque cursor.
        operation_id: Stable operation ID for contract diagnostics.

    Yields:
        Page items in server order.

    Raises:
        ResponseValidationError: If continuation metadata is inconsistent or loops.

    """
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        page = await fetch(cursor)
        for item in page.items:
            yield item
        if not page.has_more:
            return
        next_cursor = page.next_cursor
        if next_cursor is None or next_cursor in seen:
            raise ResponseValidationError(
                "The ParamPilot API returned invalid cursor continuation metadata",
                operation_id=operation_id,
            )
        seen.add(next_cursor)
        cursor = next_cursor


def iterate_cursor_sync(
    fetch: Callable[[str | None], CursorPage[T]],
    *,
    operation_id: str,
) -> Iterator[T]:
    """Lazily traverse cursor pages through a native synchronous caller.

    Args:
        fetch: Function retrieving exactly one page for an opaque cursor.
        operation_id: Stable operation ID for contract diagnostics.

    Yields:
        Page items in server order.

    Raises:
        ResponseValidationError: If continuation metadata is inconsistent or loops.

    """
    cursor: str | None = None
    seen: set[str] = set()
    while True:
        page = fetch(cursor)
        yield from page.items
        if not page.has_more:
            return
        next_cursor = page.next_cursor
        if next_cursor is None or next_cursor in seen:
            raise ResponseValidationError(
                "The ParamPilot API returned invalid cursor continuation metadata",
                operation_id=operation_id,
            )
        seen.add(next_cursor)
        cursor = next_cursor

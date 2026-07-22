"""Typed response values that retain safe transport metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

from parampilot.errors import ResponseValidationError

T = TypeVar("T")
SAFE_RESPONSE_HEADERS = frozenset(
    {
        "content-disposition",
        "content-length",
        "content-type",
        "etag",
        "idempotency-replayed",
        "location",
        "retry-after",
        "www-authenticate",
        "x-request-id",
    }
)


def safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Copy only public contract and content metadata headers.

    Args:
        headers: Complete HTTP response headers.

    Returns:
        Lowercase-keyed allowlisted response metadata without cookies.

    """
    return {
        name.lower(): value
        for name, value in headers.items()
        if name.lower() in SAFE_RESPONSE_HEADERS
    }


@dataclass(frozen=True, slots=True)
class ApiResponse(Generic[T]):
    """Validated response data plus privacy-safe HTTP metadata.

    Args:
        data: Validated operation result.
        status_code: Successful HTTP response status.
        headers: Immutable-by-convention copied response headers.
        request_id: Optional safe server correlation identifier.
        etag: Optional resource revision or artifact validator.

    """

    data: T
    status_code: int
    headers: Mapping[str, str]
    request_id: str | None
    etag: str | None

    def require_etag(self) -> str:
        """Return the declared resource revision or fail explicitly.

        Returns:
            Nonempty strong or weak response ETag.

        Raises:
            ResponseValidationError: If the operation omitted its required ETag.

        """
        if self.etag is None:
            raise ResponseValidationError(
                "The ParamPilot API response omitted the expected ETag",
                request_id=self.request_id,
            )
        return self.etag

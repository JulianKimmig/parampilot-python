"""Shared typed request, response, metadata, and capability resource helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from typing import Any, TypeVar

from pydantic import TypeAdapter, ValidationError

from parampilot.downloads import AsyncDownload
from parampilot.errors import ResponseDecodeError, ResponseValidationError
from parampilot.operations import operation
from parampilot.responses import ApiResponse, safe_response_headers
from parampilot.serialization import json_value
from parampilot.transport import AsyncTransport

T = TypeVar("T")
CapabilityChecker = Callable[[Collection[str]], Awaitable[object]]


class AsyncResource:
    """Base for cohesive async resources using generated operation metadata.

    Args:
        transport: Reusable authenticated asynchronous transport.
        capability_checker: Cached server compatibility/capability checker.

    """

    def __init__(
        self,
        transport: AsyncTransport,
        capability_checker: CapabilityChecker,
    ) -> None:
        """Store shared request dependencies.

        Args:
            transport: Reusable authenticated asynchronous transport.
            capability_checker: Cached server compatibility/capability checker.

        """
        self._transport = transport
        self._capability_checker = capability_checker

    async def _require(self, capability: str | None) -> None:
        """Require one server capability when the feature declares it.

        Args:
            capability: Stable capability name or ``None``.

        """
        if capability is not None:
            await self._capability_checker({capability})

    async def _response(
        self,
        operation_id: str,
        adapter: type[T] | TypeAdapter[T],
        *,
        path_values: Mapping[str, object] | None = None,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
        capability: str | None = None,
        allow_not_modified: bool = False,
    ) -> ApiResponse[T] | None:
        """Issue, decode, validate, and annotate one JSON operation.

        Args:
            operation_id: Stable generated operation ID.
            adapter: Pydantic model class or union adapter.
            path_values: Template values keyed by placeholder.
            params: Optional query mapping.
            body: Optional typed JSON request body.
            headers: Optional operation headers.
            files: Optional byte-backed multipart fields.
            capability: Stable capability required by this feature.
            allow_not_modified: Return ``None`` for HTTP 304.

        Returns:
            Validated result with response metadata, or ``None`` for HTTP 304.

        Raises:
            ResponseDecodeError: If successful JSON cannot be decoded.
            ResponseValidationError: If decoded data violates the contract.

        """
        await self._require(capability)
        metadata = operation(operation_id)
        response = await self._transport.request_operation(
            metadata,
            metadata.path(**dict(path_values or {})),
            params=params,
            json_body=json_value(body) if body is not None else None,
            headers=headers,
            files=files,
            allow_not_modified=allow_not_modified,
        )
        if response.status_code == 304:
            return None
        request_id = response.headers.get("X-Request-ID")
        try:
            payload = response.json()
        except ValueError as error:
            raise ResponseDecodeError(
                "The ParamPilot API returned invalid JSON",
                operation_id=operation_id,
                request_id=request_id,
            ) from error
        try:
            if isinstance(adapter, TypeAdapter):
                value = adapter.validate_python(payload)
            else:
                value = adapter.model_validate(payload)  # type: ignore[attr-defined]
        except ValidationError as error:
            raise ResponseValidationError(
                "The ParamPilot API response violated its generated contract",
                operation_id=operation_id,
                request_id=request_id,
            ) from error
        return ApiResponse(
            data=value,
            status_code=response.status_code,
            headers=safe_response_headers(response.headers),
            request_id=request_id,
            etag=response.headers.get("ETag"),
        )

    async def _model(
        self,
        operation_id: str,
        adapter: type[T] | TypeAdapter[T],
        **kwargs: Any,
    ) -> T:
        """Return only validated data for one JSON operation.

        Args:
            operation_id: Stable generated operation ID.
            adapter: Pydantic model class or union adapter.
            **kwargs: Request options accepted by ``_response``.

        Returns:
            Validated operation result.

        """
        response = await self._response(operation_id, adapter, **kwargs)
        if response is None:
            raise ResponseValidationError(
                "Unexpected not-modified response",
                operation_id=operation_id,
            )
        return response.data

    async def _empty(
        self,
        operation_id: str,
        *,
        path_values: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Issue an operation whose success has no response body.

        Args:
            operation_id: Stable generated operation ID.
            path_values: Template values keyed by placeholder.
            headers: Optional operation headers.

        """
        metadata = operation(operation_id)
        await self._transport.request_operation(
            metadata,
            metadata.path(**dict(path_values or {})),
            headers=headers,
        )

    async def _download(
        self,
        operation_id: str,
        *,
        path_values: Mapping[str, object] | None = None,
        params: Mapping[str, Any] | None = None,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
        capability: str | None = None,
        accept: str = "*/*",
        allow_not_modified: bool = False,
    ) -> AsyncDownload | None:
        """Open an unbuffered successful binary operation.

        Args:
            operation_id: Stable generated operation ID.
            path_values: Template values keyed by placeholder.
            params: Optional query mapping.
            body: Optional typed JSON request body.
            headers: Optional operation headers.
            capability: Stable capability required by this feature.
            accept: Requested response media types.
            allow_not_modified: Return ``None`` for HTTP 304.

        Returns:
            Caller-owned asynchronous download handle.

        """
        await self._require(capability)
        metadata = operation(operation_id)
        response = await self._transport.stream_operation(
            metadata,
            metadata.path(**dict(path_values or {})),
            params=params,
            json_body=json_value(body) if body is not None else None,
            headers=headers,
            accept=accept,
            allow_not_modified=allow_not_modified,
        )
        if response.status_code == 304:
            await response.aclose()
            return None
        return AsyncDownload(response)

    async def _required_download(
        self,
        operation_id: str,
        **kwargs: Any,
    ) -> AsyncDownload:
        """Open a download for an operation that cannot return HTTP 304.

        Args:
            operation_id: Stable generated operation ID.
            **kwargs: Stream request options accepted by ``_download``.

        Returns:
            Caller-owned asynchronous download handle.

        """
        download = await self._download(operation_id, **kwargs)
        if download is None:
            raise ResponseValidationError(
                "Unexpected not-modified download response",
                operation_id=operation_id,
            )
        return download

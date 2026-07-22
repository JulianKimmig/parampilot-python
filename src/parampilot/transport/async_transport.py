"""Native reusable HTTPX transport with conservative asynchronous retries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from parampilot.configuration import ClientConfiguration
from parampilot.errors import ConfigurationError
from parampilot.operations import Operation
from parampilot.transport.async_buffered import send_buffered_response
from parampilot.transport.async_streaming import open_stream_response
from parampilot.transport.headers import request_headers


class AsyncTransport:
    """Issue authenticated requests through one native asynchronous HTTPX pool.

    Args:
        configuration: Validated SDK connection and retry settings.
        http_client: Optional caller-owned HTTPX async client.

    """

    def __init__(
        self,
        configuration: ClientConfiguration,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize an owned or injected asynchronous HTTP client.

        Args:
            configuration: Validated SDK connection and retry settings.
            http_client: Optional caller-owned HTTPX async client.

        Raises:
            ConfigurationError: If ``http_client`` has the wrong modality.

        """
        if http_client is not None and not isinstance(http_client, httpx.AsyncClient):
            raise ConfigurationError("http_client must be an httpx.AsyncClient")
        self._configuration = configuration
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=configuration.timeout,
            follow_redirects=False,
        )
        self._closed = False

    @property
    def closed(self) -> bool:
        """Report whether this SDK transport has been closed.

        Returns:
            ``True`` after ``close`` has been awaited.

        """
        return self._closed

    def _headers(
        self,
        operation: Operation | None,
        values: Mapping[str, str] | None,
        *,
        accept: str,
    ) -> dict[str, str]:
        """Build one credential-safe header set reused across retries.

        Args:
            operation: Generated operation metadata when available.
            values: Caller/resource headers.
            accept: Requested response media type.

        Returns:
            Complete authenticated request headers.

        Raises:
            ConfigurationError: If callers try to override protected headers.

        """
        return request_headers(
            self._configuration,
            operation,
            values,
            accept=accept,
        )

    def _ensure_open(self) -> None:
        """Require an open transport before building a request.

        Raises:
            ConfigurationError: If this SDK client is already closed.

        """
        if self._closed:
            raise ConfigurationError("The ParamPilot client is closed")

    async def request_operation(
        self,
        operation: Operation,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
        accept: str = "application/json",
        allow_not_modified: bool = False,
    ) -> httpx.Response:
        """Issue one generated operation and apply its retry classification.

        Args:
            operation: Generated method/retry metadata.
            path: Fully rendered rooted path.
            params: Optional typed query mapping.
            json_body: Optional JSON-compatible request body.
            headers: Optional safe operation headers.
            files: Optional byte-backed multipart fields.
            accept: Requested response media type.
            allow_not_modified: Treat HTTP 304 as a non-error result.

        Returns:
            Successful buffered response, or allowed HTTP 304.

        Raises:
            TransportError: If HTTPX fails beyond the safe retry budget.
            ParamPilotHTTPError: If the server returns an unsuccessful response.

        """
        self._ensure_open()
        return await send_buffered_response(
            client=self._client,
            configuration=self._configuration,
            operation=operation,
            method=operation.method,
            path=path,
            params=params,
            json_body=json_body,
            headers=self._headers(operation, headers, accept=accept),
            files=files,
            allow_not_modified=allow_not_modified,
        )

    async def request_raw(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        accept: str = "*/*",
    ) -> httpx.Response:
        """Issue an explicitly untyped non-retrying request within public v2.

        Args:
            method: HTTP method.
            path: Rooted path beneath ``/papi/v2/``.
            params: Optional query mapping.
            json_body: Optional JSON-compatible body.
            headers: Optional safe caller headers.
            accept: Requested response media type.

        Returns:
            Successful raw HTTPX response.

        Raises:
            ConfigurationError: If ``path`` escapes the public v2 boundary.

        """
        if not path.startswith("/papi/v2/"):
            raise ConfigurationError("Advanced requests must stay beneath /papi/v2/")
        self._ensure_open()
        return await send_buffered_response(
            client=self._client,
            configuration=self._configuration,
            operation=None,
            method=method.upper(),
            path=path,
            params=params,
            json_body=json_body,
            headers=self._headers(None, headers, accept=accept),
            files=None,
            allow_not_modified=False,
        )

    async def stream_operation(
        self,
        operation: Operation,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        accept: str = "*/*",
        allow_not_modified: bool = False,
    ) -> httpx.Response:
        """Open an unbuffered successful operation response.

        Args:
            operation: Generated method/retry metadata.
            path: Fully rendered rooted path.
            params: Optional query mapping.
            json_body: Optional JSON-compatible request body.
            headers: Optional safe operation headers.
            accept: Requested response media type.
            allow_not_modified: Treat HTTP 304 as a non-error result.

        Returns:
            Open streaming HTTPX response owned by the caller.

        """
        self._ensure_open()
        return await open_stream_response(
            client=self._client,
            configuration=self._configuration,
            operation=operation,
            path=path,
            params=params,
            json_body=json_body,
            headers=self._headers(operation, headers, accept=accept),
            allow_not_modified=allow_not_modified,
        )

    async def request_json(self, method: str, path: str) -> dict[str, Any]:
        """Retain the foundation's raw JSON-object helper for compatibility.

        Args:
            method: HTTP method.
            path: Rooted public v2 path.

        Returns:
            Decoded JSON object.

        Raises:
            ConfigurationError: If the response is not an object.

        """
        response = await self.request_raw(method, path, accept="application/json")
        value = response.json()
        if not isinstance(value, dict):
            raise ConfigurationError("The ParamPilot API returned non-object JSON")
        return value

    async def close(self) -> None:
        """Close only an HTTP client owned by this SDK transport."""
        if self._closed:
            return
        if self._owns_client:
            await self._client.aclose()
        self._closed = True

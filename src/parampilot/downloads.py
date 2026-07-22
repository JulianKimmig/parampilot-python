"""Unbuffered asynchronous download handles for public binary responses."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from parampilot.download_metadata import response_content_length, response_filename
from parampilot.errors import ConfigurationError


class AsyncDownload:
    """Single-consumer unbuffered asynchronous response stream.

    Args:
        response: Open successful HTTPX response created with ``stream=True``.

    """

    def __init__(self, response: httpx.Response) -> None:
        """Initialize safe metadata without reading response bytes.

        Args:
            response: Open successful streaming response.

        """
        self._response = response
        self._started = False
        self._closed = False
        self.filename = response_filename(response)
        self.content_type = response.headers.get("Content-Type")
        self.content_length = response_content_length(response)
        self.etag = response.headers.get("ETag")
        self.request_id = response.headers.get("X-Request-ID")

    @property
    def closed(self) -> bool:
        """Report whether the underlying response has been released.

        Returns:
            ``True`` after consumption or explicit close.

        """
        return self._closed

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        """Yield response bytes once and always release the connection.

        Yields:
            Nonempty response chunks in transport order.

        Raises:
            ConfigurationError: If the stream is closed or already consumed.

        """
        if self._closed or self._started:
            raise ConfigurationError("This ParamPilot download is already consumed")
        self._started = True
        try:
            async for chunk in self._response.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await self.close()

    async def read(self) -> bytes:
        """Explicitly buffer the complete response in memory.

        Returns:
            Complete downloaded bytes.

        """
        chunks = [chunk async for chunk in self.aiter_bytes()]
        return b"".join(chunks)

    async def write_to(self, path: str | Path, *, overwrite: bool = False) -> Path:
        """Stream bytes to an explicit local path.

        Args:
            path: Caller-selected destination file.
            overwrite: Replace an existing file only when explicitly enabled.

        Returns:
            Normalized destination ``Path``.

        Raises:
            FileExistsError: If the path exists and overwrite is false.

        """
        destination = Path(path)
        mode = "wb" if overwrite else "xb"
        try:
            # Local chunk writes remain bounded by the transport's chunk size.
            with destination.open(mode) as output:  # noqa: ASYNC230
                async for chunk in self.aiter_bytes():
                    output.write(chunk)
        finally:
            await self.close()
        return destination

    async def close(self) -> None:
        """Release the response and its pooled connection exactly once."""
        if self._closed:
            return
        await self._response.aclose()
        self._closed = True

    async def __aenter__(self) -> AsyncDownload:
        """Enter the open download context.

        Returns:
            This download handle.

        """
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Release the response on context exit.

        Args:
            exc_type: Active exception type, if any.
            exc_value: Active exception value, if any.
            traceback: Active traceback, if any.

        """
        await self.close()

    def __repr__(self) -> str:
        """Return a URL- and credential-free diagnostic representation.

        Returns:
            Safe stream metadata and closure state.

        """
        return (
            f"AsyncDownload(filename={self.filename!r}, "
            f"content_type={self.content_type!r}, closed={self.closed!r})"
        )

"""Unbuffered synchronous download handles for public binary responses."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx

from parampilot.download_metadata import response_content_length, response_filename
from parampilot.errors import ConfigurationError


class Download:
    """Single-consumer unbuffered synchronous response stream.

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

    def iter_bytes(self) -> Iterator[bytes]:
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
            for chunk in self._response.iter_bytes():
                if chunk:
                    yield chunk
        finally:
            self.close()

    def read(self) -> bytes:
        """Explicitly buffer the complete response in memory.

        Returns:
            Complete downloaded bytes.

        """
        return b"".join(self.iter_bytes())

    def write_to(self, path: str | Path, *, overwrite: bool = False) -> Path:
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
            with destination.open(mode) as output:
                for chunk in self.iter_bytes():
                    output.write(chunk)
        finally:
            self.close()
        return destination

    def close(self) -> None:
        """Release the response and its pooled connection exactly once."""
        if self._closed:
            return
        self._response.close()
        self._closed = True

    def __enter__(self) -> Download:
        """Enter the open download context.

        Returns:
            This download handle.

        """
        return self

    def __exit__(
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
        self.close()

    def __repr__(self) -> str:
        """Return a URL- and credential-free diagnostic representation.

        Returns:
            Safe stream metadata and closure state.

        """
        return (
            f"Download(filename={self.filename!r}, "
            f"content_type={self.content_type!r}, closed={self.closed!r})"
        )

"""Streaming download tests for asynchronous experiment and model artifacts."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from parampilot import AsyncParamPilot
from parampilot.downloads import AsyncDownload
from tests.support import CAMPAIGN_ID, TOKEN


class TrackingStream(httpx.AsyncByteStream):
    """External response stream that records consumption and closure."""

    def __init__(self, chunks: list[bytes]) -> None:
        """Store chunks for later lazy iteration.

        Args:
            chunks: Byte chunks exposed to HTTPX.

        """
        self._chunks = chunks
        self.yielded = 0
        self.closed = False

    async def __aiter__(self):  # type: ignore[no-untyped-def]
        """Yield configured chunks while recording demand."""
        for chunk in self._chunks:
            self.yielded += 1
            yield chunk

    async def aclose(self) -> None:
        """Record HTTPX stream closure."""
        self.closed = True


@pytest.mark.asyncio
async def test_export_returns_unbuffered_stream_and_closes_after_iteration() -> None:
    """Streaming exports must not consume bytes before the caller iterates."""
    stream = TrackingStream([b"a,b\n", b"1,2\n"])

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a lazily consumed CSV response.

        Args:
            request: Outbound export request.

        Returns:
            Streaming HTTPX response.

        """
        assert request.url.params["format"] == "csv"
        return httpx.Response(
            200,
            stream=stream,
            headers={
                "Content-Type": "text/csv",
                "Content-Disposition": 'attachment; filename="experiments.csv"',
                "ETag": '"export-v1"',
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    download = await client.experiments.export(CAMPAIGN_ID, format="csv")

    assert isinstance(download, AsyncDownload)
    assert download.filename == "experiments.csv"
    assert download.content_type == "text/csv"
    assert download.etag == '"export-v1"'
    assert stream.yielded == 0
    content = b"".join([chunk async for chunk in download.aiter_bytes()])
    assert content == b"a,b\n1,2\n"
    assert stream.closed is True
    assert download.closed is True
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_stream_write_uses_exclusive_path_and_closes_response(
    tmp_path: Path,
) -> None:
    """Explicit path writing must avoid silent overwrite and release the response.

    Args:
        tmp_path: Pytest-managed output directory.

    """
    streams = [TrackingStream([b"payload"]), TrackingStream([b"replacement"])]

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return the next configured byte stream.

        Args:
            request: Outbound export request.

        Returns:
            Streaming response associated with ``request``.

        """
        return httpx.Response(
            200,
            stream=streams.pop(0),
            headers={"Content-Type": "application/octet-stream"},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )
    target = tmp_path / "export.bin"

    first = await client.experiments.export(CAMPAIGN_ID, format="xlsx")
    written = await first.write_to(target)
    second = await client.experiments.export(CAMPAIGN_ID, format="xlsx")

    assert written == target
    assert target.read_bytes() == b"payload"
    with pytest.raises(FileExistsError):
        await second.write_to(target)
    assert second.closed is True
    await client.close()
    await http_client.aclose()

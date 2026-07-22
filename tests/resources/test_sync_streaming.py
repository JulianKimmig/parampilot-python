"""Streaming download behavior for synchronous public resources."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from parampilot import Download, ParamPilot
from tests.support import CAMPAIGN_ID, TOKEN


class TrackingSyncStream(httpx.SyncByteStream):
    """External synchronous response stream recording demand and closure."""

    def __init__(self, chunks: list[bytes]) -> None:
        """Store chunks for lazy iteration.

        Args:
            chunks: Byte chunks exposed to HTTPX.

        """
        self._chunks = chunks
        self.yielded = 0
        self.closed = False

    def __iter__(self):  # type: ignore[no-untyped-def]
        """Yield configured chunks while recording demand."""
        for chunk in self._chunks:
            self.yielded += 1
            yield chunk

    def close(self) -> None:
        """Record HTTPX stream closure."""
        self.closed = True


def test_sync_export_is_unbuffered_single_consumer_and_closes() -> None:
    """A sync export must stream only on demand and release its connection."""
    stream = TrackingSyncStream([b"a,b\n", b"1,2\n"])

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a lazily consumed CSV stream.

        Args:
            request: Outbound export request.

        Returns:
            Open streaming HTTPX response.

        """
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

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    download = client.experiments.export(CAMPAIGN_ID, format="csv")

    assert isinstance(download, Download)
    assert download.filename == "experiments.csv"
    assert download.etag == '"export-v1"'
    assert stream.yielded == 0
    assert b"".join(download.iter_bytes()) == b"a,b\n1,2\n"
    assert stream.closed is True
    assert download.closed is True
    client.close()
    http_client.close()


def test_sync_stream_write_uses_exclusive_path_and_closes(
    tmp_path: Path,
) -> None:
    """Sync path writing must require overwrite opt-in and close on failure.

    Args:
        tmp_path: Pytest-managed output directory.

    """
    streams = [TrackingSyncStream([b"payload"]), TrackingSyncStream([b"new"])]

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the next configured stream.

        Args:
            request: Outbound export request.

        Returns:
            Streaming response associated with the request.

        """
        return httpx.Response(200, stream=streams.pop(0), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )
    target = tmp_path / "export.bin"

    first = client.experiments.export(CAMPAIGN_ID, format="xlsx")
    assert first.write_to(target) == target
    second = client.experiments.export(CAMPAIGN_ID, format="xlsx")

    assert target.read_bytes() == b"payload"
    with pytest.raises(FileExistsError):
        second.write_to(target)
    assert second.closed is True
    client.close()
    http_client.close()

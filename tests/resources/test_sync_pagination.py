"""Lazy cursor-pagination behavior for synchronous resource collections."""

from __future__ import annotations

import httpx
import pytest

from parampilot import ParamPilot
from parampilot.errors import ConfigurationError, ResponseValidationError
from tests.support import TOKEN, campaign_summary_payload


def test_sync_campaign_iterator_is_lazy_and_follows_opaque_cursor() -> None:
    """Sync iteration must fetch bounded pages lazily without cursor rewriting."""
    cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return two pages keyed by the exact opaque cursor.

        Args:
            request: Outbound collection request.

        Returns:
            First or terminal campaign page.

        """
        cursor = request.url.params.get("cursor")
        cursors.append(cursor)
        assert request.url.params["limit"] == "2"
        if cursor is None:
            payload = {
                "items": [campaign_summary_payload(name="first")],
                "next_cursor": "opaque.cursor+/=",
                "has_more": True,
                "snapshot_at": "2026-07-14T12:00:00Z",
            }
        else:
            payload = {
                "items": [campaign_summary_payload(name="second")],
                "next_cursor": None,
                "has_more": False,
                "snapshot_at": "2026-07-14T12:00:00Z",
            }
        return httpx.Response(200, json=payload, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    iterator = client.campaigns.iterate(limit=2)
    assert cursors == []
    names = [campaign.name for campaign in iterator]

    assert names == ["first", "second"]
    assert cursors == [None, "opaque.cursor+/="]
    client.close()
    http_client.close()


@pytest.mark.parametrize("limit", [0, 501, True])
def test_sync_invalid_page_limit_fails_before_network(limit: int) -> None:
    """Sync page methods must share the local 1-through-500 bound.

    Args:
        limit: Invalid page-size candidate.

    """
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        """Count any unexpected network access.

        Args:
            request: Unexpected outbound request.

        Returns:
            Response that must remain unreachable.

        """
        nonlocal requests
        requests += 1
        return httpx.Response(500, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ConfigurationError, match="limit"):
        client.campaigns.list(limit=limit)

    assert requests == 0
    client.close()
    http_client.close()


def test_sync_cursor_loop_is_rejected_after_yielding_the_received_page() -> None:
    """Repeated opaque continuation state must raise a typed response error."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the same looping continuation cursor every time.

        Args:
            request: Outbound collection request.

        Returns:
            Nonterminal looping cursor page.

        """
        return httpx.Response(
            200,
            json={
                "items": [campaign_summary_payload(name="item")],
                "next_cursor": "same",
                "has_more": True,
                "snapshot_at": "2026-07-14T12:00:00Z",
            },
            request=request,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    iterator = client.campaigns.iterate(limit=1)
    assert next(iterator).name == "item"
    assert next(iterator).name == "item"
    with pytest.raises(ResponseValidationError, match="cursor"):
        next(iterator)

    client.close()
    http_client.close()

"""Lazy cursor-pagination behavior for asynchronous resource collections."""

from __future__ import annotations

import httpx
import pytest

from parampilot import AsyncParamPilot
from parampilot.errors import ConfigurationError
from parampilot.models import CampaignPageResponse
from tests.support import TOKEN, campaign_summary_payload


@pytest.mark.asyncio
async def test_campaign_iterator_is_lazy_bounded_and_follows_opaque_cursor() -> None:
    """Iteration must request one bounded page at a time without cursor rewriting."""
    cursors: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
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
                "items": [
                    campaign_summary_payload(name="first"),
                    campaign_summary_payload(name="second"),
                ],
                "next_cursor": "opaque.cursor+/=",
                "has_more": True,
                "snapshot_at": "2026-07-14T12:00:00Z",
            }
        else:
            payload = {
                "items": [campaign_summary_payload(name="third")],
                "next_cursor": None,
                "has_more": False,
                "snapshot_at": "2026-07-14T12:00:00Z",
            }
        return httpx.Response(200, json=payload, request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    iterator = client.campaigns.iterate(limit=2)
    assert cursors == []
    names = [campaign.name async for campaign in iterator]

    assert names == ["first", "second", "third"]
    assert cursors == [None, "opaque.cursor+/="]
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_page_method_returns_typed_page_without_eager_followup() -> None:
    """Explicit page access must return one typed page and stop."""
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a page that advertises another cursor.

        Args:
            request: Outbound collection request.

        Returns:
            One nonterminal campaign page.

        """
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "items": [campaign_summary_payload(name="first")],
                "next_cursor": "next",
                "has_more": True,
                "snapshot_at": "2026-07-14T12:00:00Z",
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    page = await client.campaigns.list(limit=1)

    assert isinstance(page, CampaignPageResponse)
    assert page.has_more is True
    assert requests == 1
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_breaking_iteration_does_not_prefetch_next_page() -> None:
    """Consumer cancellation after one item must not request a later page."""
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a nonterminal page while counting calls.

        Args:
            request: Outbound collection request.

        Returns:
            One nonterminal campaign page.

        """
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "items": [campaign_summary_payload(name="first")],
                "next_cursor": "next",
                "has_more": True,
                "snapshot_at": "2026-07-14T12:00:00Z",
            },
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    async for _campaign in client.campaigns.iterate(limit=1):
        break

    assert requests == 1
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 501, True])
async def test_invalid_page_limit_fails_before_network(limit: int) -> None:
    """Collection bounds must be enforced locally for every typed page call.

    Args:
        limit: Invalid page-size candidate.

    """
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        """Count any unexpected request.

        Args:
            request: Unexpected outbound request.

        Returns:
            Response that should never be reached.

        """
        nonlocal requests
        requests += 1
        return httpx.Response(500, request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    with pytest.raises(ConfigurationError, match="limit"):
        await client.campaigns.list(limit=limit)

    assert requests == 0
    await client.close()
    await http_client.aclose()

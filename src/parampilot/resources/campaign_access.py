"""Asynchronous campaign collaborator grant operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from parampilot.models import (
    CampaignAccessGrantPageResponse,
    CampaignAccessGrantRequest,
    CampaignAccessGrantResponse,
)
from parampilot.pagination import iterate_cursor
from parampilot.resources.base import AsyncResource
from parampilot.resources.headers import mutation_headers
from parampilot.serialization import page_limit, public_id


class CampaignAccessResource(AsyncResource):
    """Typed asynchronous campaign collaborator grant resource."""

    async def list(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> CampaignAccessGrantPageResponse:
        """Fetch one bounded page of campaign access grants.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.
            cursor: Opaque continuation cursor.

        Returns:
            Typed access-grant page.

        """
        return await self._model(
            "listCampaignAccessGrants",
            CampaignAccessGrantPageResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={"limit": page_limit(limit), "cursor": cursor},
        )

    def iterate(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
    ) -> AsyncIterator[CampaignAccessGrantResponse]:
        """Lazily iterate all visible access grants.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.

        Returns:
            Lazy asynchronous access-grant iterator.

        """

        async def fetch(cursor: str | None) -> CampaignAccessGrantPageResponse:
            """Fetch one grant page.

            Args:
                cursor: Opaque continuation cursor.

            Returns:
                Typed access-grant page.

            """
            return await self.list(campaign_id, limit=limit, cursor=cursor)

        return iterate_cursor(fetch, operation_id="listCampaignAccessGrants")

    async def upsert(
        self,
        campaign_id: UUID | str,
        request: CampaignAccessGrantRequest,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignAccessGrantResponse:
        """Create or replace one collaborator grant.

        Args:
            campaign_id: Public campaign UUID.
            request: Collaborator username and access level.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Created or updated grant.

        """
        return await self._model(
            "upsertCampaignAccessGrant",
            CampaignAccessGrantResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=request,
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

    async def delete(
        self,
        campaign_id: UUID | str,
        grant_id: UUID | str,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> None:
        """Delete one collaborator grant.

        Args:
            campaign_id: Public campaign UUID.
            grant_id: Public grant UUID.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        """
        await self._empty(
            "deleteCampaignAccessGrant",
            path_values={
                "campaign_id": public_id(campaign_id, label="campaign_id"),
                "grant_id": public_id(grant_id, label="grant_id"),
            },
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

"""Asynchronous campaign transfer-link mutation operations."""

from __future__ import annotations

from uuid import UUID

from parampilot.models import CampaignResponse, CampaignTransferLinkRequest
from parampilot.resources.base import AsyncResource
from parampilot.resources.headers import mutation_headers
from parampilot.serialization import public_id


class CampaignTransferLinksResource(AsyncResource):
    """Typed asynchronous campaign transfer-link resource."""

    async def create(
        self,
        campaign_id: UUID | str,
        request: CampaignTransferLinkRequest,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Create one validated source-to-target campaign transfer mapping.

        Args:
            campaign_id: Public target campaign UUID.
            request: Validated source campaign mapping.
            if_match: Current strong target campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated target campaign.

        """
        return await self._model(
            "createCampaignTransferLink",
            CampaignResponse,
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
        link_id: UUID | str,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Delete one transfer link without scheduling training.

        Args:
            campaign_id: Public target campaign UUID.
            link_id: Public transfer-link UUID.
            if_match: Current strong target campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated target campaign.

        """
        return await self._model(
            "deleteCampaignTransferLink",
            CampaignResponse,
            path_values={
                "campaign_id": public_id(campaign_id, label="campaign_id"),
                "link_id": public_id(link_id, label="link_id"),
            },
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

"""Asynchronous campaign collection, detail, and lifecycle operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from parampilot.errors import ResponseValidationError
from parampilot.models import (
    CampaignCreateRequest,
    CampaignPageResponse,
    CampaignResponse,
    CampaignStatusResponse,
    CampaignSummaryResponse,
    ConfiguredCampaignCreateRequest,
    EmptyRequest,
)
from parampilot.pagination import iterate_cursor
from parampilot.resources.campaign_configuration import (
    CampaignConfigurationMethods,
)
from parampilot.resources.headers import mutation_headers
from parampilot.responses import ApiResponse
from parampilot.serialization import page_limit, public_id


class CampaignsResource(CampaignConfigurationMethods):
    """Typed asynchronous access to campaign resources and configuration."""

    async def create(
        self,
        request: CampaignCreateRequest,
        *,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Create one draft campaign without starting or training it.

        Args:
            request: Validated draft campaign metadata.
            idempotency_key: Optional logical mutation key.

        Returns:
            Created campaign representation.

        """
        return await self._model(
            "createCampaign",
            CampaignResponse,
            body=request,
            headers=mutation_headers(idempotency=idempotency_key),
        )

    async def create_configured(
        self,
        request: ConfiguredCampaignCreateRequest,
        *,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Atomically create a configured draft campaign without training.

        Args:
            request: Domain, strategy, additional fields, effects, and metadata.
            idempotency_key: Optional logical mutation key.

        Returns:
            Created configured campaign.

        """
        return await self._model(
            "createConfiguredCampaign",
            CampaignResponse,
            body=request,
            headers=mutation_headers(idempotency=idempotency_key),
            capability="campaigns.configured-create",
        )

    async def list(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> CampaignPageResponse:
        """Fetch one bounded campaign page.

        Args:
            limit: Page size from 1 through 500.
            cursor: Opaque continuation cursor returned by the server.

        Returns:
            Typed campaign page.

        """
        return await self._model(
            "listCampaigns",
            CampaignPageResponse,
            params={"limit": page_limit(limit), "cursor": cursor},
        )

    def iterate(self, *, limit: int = 100) -> AsyncIterator[CampaignSummaryResponse]:
        """Lazily iterate all visible campaigns one bounded page at a time.

        Args:
            limit: Page size from 1 through 500.

        Returns:
            Lazy asynchronous campaign iterator.

        """

        async def fetch(cursor: str | None) -> CampaignPageResponse:
            """Fetch one campaign page.

            Args:
                cursor: Opaque continuation cursor.

            Returns:
                Typed campaign page.

            """
            return await self.list(limit=limit, cursor=cursor)

        return iterate_cursor(fetch, operation_id="listCampaigns")

    async def get(self, campaign_id: UUID | str) -> CampaignResponse:
        """Retrieve one complete campaign representation.

        Args:
            campaign_id: Public campaign UUID.

        Returns:
            Typed campaign representation.

        """
        return (await self.get_with_metadata(campaign_id)).data

    async def get_with_metadata(
        self,
        campaign_id: UUID | str,
    ) -> ApiResponse[CampaignResponse]:
        """Retrieve a campaign plus its ETag and correlation metadata.

        Args:
            campaign_id: Public campaign UUID.

        Returns:
            Typed campaign response with safe HTTP metadata.

        """
        response = await self._response(
            "getCampaign",
            CampaignResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
        )
        if response is None:
            raise ResponseValidationError(
                "Unexpected not-modified campaign response",
                operation_id="getCampaign",
            )
        return response

    async def get_status(self, campaign_id: UUID | str) -> CampaignStatusResponse:
        """Retrieve campaign lifecycle and model-freshness status.

        Args:
            campaign_id: Public campaign UUID.

        Returns:
            Typed status representation.

        """
        return await self._model(
            "getCampaignStatus",
            CampaignStatusResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
        )

    async def start(
        self,
        campaign_id: UUID | str,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Start a configured campaign without fitting a model.

        Args:
            campaign_id: Public campaign UUID.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated started campaign.

        """
        return await self._lifecycle(
            "startCampaign",
            campaign_id,
            if_match=if_match,
            idempotency_key=idempotency_key,
        )

    async def unlock(
        self,
        campaign_id: UUID | str,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Unlock an eligible campaign without fitting a model.

        Args:
            campaign_id: Public campaign UUID.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated unlocked campaign.

        """
        return await self._lifecycle(
            "unlockCampaign",
            campaign_id,
            if_match=if_match,
            idempotency_key=idempotency_key,
        )

    async def _lifecycle(
        self,
        operation_id: str,
        campaign_id: UUID | str,
        *,
        if_match: str,
        idempotency_key: str | None,
    ) -> CampaignResponse:
        """Apply one non-training campaign lifecycle transition.

        Args:
            operation_id: Start or unlock operation ID.
            campaign_id: Public campaign UUID.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated campaign.

        """
        return await self._model(
            operation_id,
            CampaignResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=EmptyRequest(),
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

    async def archive(
        self,
        campaign_id: UUID | str,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> None:
        """Archive a campaign without scheduling model training.

        Args:
            campaign_id: Public campaign UUID.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        """
        await self._empty(
            "archiveCampaign",
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

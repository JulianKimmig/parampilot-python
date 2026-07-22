"""Synchronous campaign domain, strategy, metadata, and effect replacements."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from parampilot.models import (
    CampaignEffectRequest,
    CampaignResponse,
    CampaignSettingsRequest,
    Domain,
    ExtraData,
)
from parampilot.resources.headers import mutation_headers
from parampilot.serialization import public_id
from parampilot.sync_resources.base import SyncResource
from parampilot.types import Strategy


class SyncCampaignConfigurationMethods(SyncResource):
    """Typed complete-replacement operations mixed into sync campaigns."""

    def replace_domain(
        self,
        campaign_id: UUID | str,
        domain: Domain,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Replace a campaign's complete optimization domain.

        Args:
            campaign_id: Public campaign UUID.
            domain: Fully validated BoFire domain.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated campaign representation.

        """
        return self._model(
            "replaceCampaignDomain",
            CampaignResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=domain,
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

    def replace_strategy(
        self,
        campaign_id: UUID | str,
        strategy: Strategy,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Replace a campaign's complete discriminated strategy.

        Args:
            campaign_id: Public campaign UUID.
            strategy: Validated BoFire strategy subtype.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated campaign representation.

        """
        return self._model(
            "replaceCampaignStrategy",
            CampaignResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=strategy,
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

    def replace_additional_fields(
        self,
        campaign_id: UUID | str,
        additional_fields: ExtraData,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Replace the campaign's complete additional-field schema.

        Args:
            campaign_id: Public campaign UUID.
            additional_fields: Validated ParamPilot additional fields.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated campaign representation.

        """
        return self._model(
            "replaceCampaignAdditionalFields",
            CampaignResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=additional_fields,
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

    def replace_effects(
        self,
        campaign_id: UUID | str,
        effects: Sequence[CampaignEffectRequest],
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Replace ordered automatic campaign-effect expressions.

        Args:
            campaign_id: Public campaign UUID.
            effects: Ordered validated effect requests.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated campaign representation.

        """
        return self._model(
            "replaceCampaignEffects",
            CampaignResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=effects,
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
            capability="campaigns.effects",
        )

    def update_settings(
        self,
        campaign_id: UUID | str,
        settings: CampaignSettingsRequest,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> CampaignResponse:
        """Replace mutable campaign metadata and settings.

        Args:
            campaign_id: Public campaign UUID.
            settings: Validated complete settings request.
            if_match: Current strong campaign ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated campaign representation.

        """
        return self._model(
            "updateCampaignSettings",
            CampaignResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=settings,
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

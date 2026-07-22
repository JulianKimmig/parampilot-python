"""Synchronous experiment exports and effective-dataset operations."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from parampilot.models import (
    EffectiveExperimentExportRequest,
    EffectiveExperimentPageResponse,
    EffectiveExperimentQueryRequest,
)
from parampilot.serialization import public_id
from parampilot.sync_downloads import Download
from parampilot.sync_resources.base import SyncResource

ExportFormat = Literal["csv", "xlsx"]


class SyncExperimentExportMethods(SyncResource):
    """Streaming and effective-data methods mixed into sync experiments."""

    def export(
        self,
        campaign_id: UUID | str,
        *,
        format: ExportFormat = "csv",
        include: str | None = None,
    ) -> Download:
        """Open a reproducible unbuffered experiment export.

        Args:
            campaign_id: Public campaign UUID.
            format: CSV or XLSX output format.
            include: Optional server-declared column inclusion selector.

        Returns:
            Caller-owned synchronous download stream.

        """
        return self._required_download(
            "exportExperiments",
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={"format": format, "include": include},
            accept=(
                "text/csv, "
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    def query_effective(
        self,
        campaign_id: UUID | str,
        request: EffectiveExperimentQueryRequest | None = None,
    ) -> EffectiveExperimentPageResponse:
        """Query one bounded page of grouped transfer-aware experiment rows.

        Args:
            campaign_id: Public campaign UUID.
            request: Optional validated grouping, transfer, and cursor options.

        Returns:
            Typed effective-experiment page.

        """
        return self._model(
            "queryEffectiveExperiments",
            EffectiveExperimentPageResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=request or EffectiveExperimentQueryRequest(),
            capability="experiments.effective",
        )

    def export_effective(
        self,
        campaign_id: UUID | str,
        request: EffectiveExperimentExportRequest | None = None,
        *,
        format: ExportFormat = "csv",
    ) -> Download:
        """Open a reproducible unbuffered effective-dataset export.

        Args:
            campaign_id: Public campaign UUID.
            request: Optional validated grouping and transfer options.
            format: CSV or XLSX output format.

        Returns:
            Caller-owned synchronous download stream.

        """
        return self._required_download(
            "exportEffectiveExperiments",
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={"format": format},
            body=request or EffectiveExperimentExportRequest(),
            capability="experiments.effective",
            accept=(
                "text/csv, "
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

"""Asynchronous experiment exports and effective-dataset operations."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from parampilot.downloads import AsyncDownload
from parampilot.models import (
    EffectiveExperimentExportRequest,
    EffectiveExperimentPageResponse,
    EffectiveExperimentQueryRequest,
)
from parampilot.resources.base import AsyncResource
from parampilot.serialization import public_id

ExportFormat = Literal["csv", "xlsx"]


class ExperimentExportMethods(AsyncResource):
    """Streaming and effective-data methods mixed into experiment resources."""

    async def export(
        self,
        campaign_id: UUID | str,
        *,
        format: ExportFormat = "csv",
        include: str | None = None,
    ) -> AsyncDownload:
        """Open a reproducible unbuffered experiment export.

        Args:
            campaign_id: Public campaign UUID.
            format: CSV or XLSX output format.
            include: Optional server-declared column inclusion selector.

        Returns:
            Caller-owned asynchronous download stream.

        """
        return await self._required_download(
            "exportExperiments",
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={"format": format, "include": include},
            accept=(
                "text/csv, "
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    async def query_effective(
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
        return await self._model(
            "queryEffectiveExperiments",
            EffectiveExperimentPageResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=request or EffectiveExperimentQueryRequest(),
            capability="experiments.effective",
        )

    async def export_effective(
        self,
        campaign_id: UUID | str,
        request: EffectiveExperimentExportRequest | None = None,
        *,
        format: ExportFormat = "csv",
    ) -> AsyncDownload:
        """Open a reproducible unbuffered effective-dataset export.

        Args:
            campaign_id: Public campaign UUID.
            request: Optional validated grouping and transfer options.
            format: CSV or XLSX output format.

        Returns:
            Caller-owned asynchronous download stream.

        """
        return await self._required_download(
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

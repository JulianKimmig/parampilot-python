"""Synchronous conditional model-artifact reads and downloads."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from parampilot.models import ShapResultsResponse
from parampilot.resources.headers import revalidation_headers
from parampilot.responses import ApiResponse
from parampilot.serialization import public_id
from parampilot.sync_downloads import Download
from parampilot.sync_resources.base import SyncResource

GridFormat = Literal["arrow", "json"]


class SyncModelArtifactsResource(SyncResource):
    """Typed synchronous model grid and explanation artifacts."""

    def download_grid_predictions(
        self,
        campaign_id: UUID | str,
        *,
        format: GridFormat = "arrow",
        if_none_match: str | None = None,
    ) -> Download | None:
        """Open current grid predictions without buffering the artifact.

        Args:
            campaign_id: Public campaign UUID.
            format: Arrow stream or JSON grid representation.
            if_none_match: Optional cached artifact ETag.

        Returns:
            Open download, or ``None`` when the artifact is unchanged.

        Raises:
            TrainingRequiredError: If the current model artifact is unavailable.

        """
        return self._download(
            "downloadGridPredictions",
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={"format": format},
            headers=revalidation_headers(if_none_match),
            capability="artifacts.grid-predictions",
            accept=(
                "application/vnd.apache.arrow.stream, application/json"
                if format == "arrow"
                else "application/json"
            ),
            allow_not_modified=True,
        )

    def get_shap_results(
        self,
        campaign_id: UUID | str,
        *,
        if_none_match: str | None = None,
    ) -> ShapResultsResponse | None:
        """Retrieve typed SHAP results conditionally.

        Args:
            campaign_id: Public campaign UUID.
            if_none_match: Optional cached artifact ETag.

        Returns:
            Typed results, or ``None`` when the artifact is unchanged.

        Raises:
            TrainingRequiredError: If the current model artifact is unavailable.

        """
        response = self.get_shap_results_with_metadata(
            campaign_id,
            if_none_match=if_none_match,
        )
        return response.data if response is not None else None

    def get_shap_results_with_metadata(
        self,
        campaign_id: UUID | str,
        *,
        if_none_match: str | None = None,
    ) -> ApiResponse[ShapResultsResponse] | None:
        """Retrieve typed SHAP results plus ETag and request metadata.

        Args:
            campaign_id: Public campaign UUID.
            if_none_match: Optional cached artifact ETag.

        Returns:
            Typed response metadata, or ``None`` for HTTP 304.

        """
        return self._response(
            "getShapResults",
            ShapResultsResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            headers=revalidation_headers(if_none_match),
            capability="artifacts.shap-results",
            allow_not_modified=True,
        )

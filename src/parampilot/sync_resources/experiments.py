"""Synchronous experiment collection, import, detail, and mutation operations."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Literal
from uuid import UUID

from parampilot.errors import ResponseValidationError
from parampilot.models import (
    ExperimentBatchResponse,
    ExperimentBatchUpsertRequest,
    ExperimentDeleteResponse,
    ExperimentPageResponse,
    ExperimentPatchRequest,
    ExperimentResponse,
)
from parampilot.pagination import iterate_cursor_sync
from parampilot.resources.headers import mutation_headers
from parampilot.responses import ApiResponse
from parampilot.serialization import page_limit, public_id
from parampilot.sync_resources.experiment_imports import SyncExperimentImportMethods

ExperimentStatus = Literal["pending", "done", "invalid"]


class SyncExperimentsResource(SyncExperimentImportMethods):
    """Typed synchronous experiment resource including streamed exports."""

    def list(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
        cursor: str | None = None,
        status: ExperimentStatus | None = None,
        ids: Sequence[UUID | str] | None = None,
        include_transfer: bool = False,
    ) -> ExperimentPageResponse:
        """Fetch one bounded filtered experiment page.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.
            cursor: Opaque continuation cursor.
            status: Optional closed experiment-status filter.
            ids: Optional repeated public experiment IDs.
            include_transfer: Include effective transfer rows when true.

        Returns:
            Typed experiment page.

        """
        normalized_ids = (
            [public_id(value, label="ids") for value in ids]
            if ids is not None
            else None
        )
        return self._model(
            "listExperiments",
            ExperimentPageResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={
                "limit": page_limit(limit),
                "cursor": cursor,
                "status": status,
                "ids": normalized_ids,
                "include_transfer": include_transfer,
            },
        )

    def iterate(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
        status: ExperimentStatus | None = None,
        ids: Sequence[UUID | str] | None = None,
        include_transfer: bool = False,
    ) -> Iterator[ExperimentResponse]:
        """Lazily iterate experiments using stable filters and bounded pages.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.
            status: Optional closed experiment-status filter.
            ids: Optional repeated public experiment IDs.
            include_transfer: Include effective transfer rows when true.

        Returns:
            Lazy synchronous experiment iterator.

        """

        def fetch(cursor: str | None) -> ExperimentPageResponse:
            """Fetch one experiment page.

            Args:
                cursor: Opaque continuation cursor.

            Returns:
                Typed experiment page.

            """
            return self.list(
                campaign_id,
                limit=limit,
                cursor=cursor,
                status=status,
                ids=ids,
                include_transfer=include_transfer,
            )

        return iterate_cursor_sync(fetch, operation_id="listExperiments")

    def batch_upsert(
        self,
        campaign_id: UUID | str,
        request: ExperimentBatchUpsertRequest,
        *,
        idempotency_key: str | None = None,
    ) -> ExperimentBatchResponse:
        """Atomically create or update an ordered bounded experiment batch.

        Args:
            campaign_id: Public campaign UUID.
            request: One through 500 validated experiment rows.
            idempotency_key: Optional logical mutation key.

        Returns:
            Ordered one-to-one atomic batch results.

        """
        return self._model(
            "batchUpsertExperiments",
            ExperimentBatchResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=request,
            headers=mutation_headers(idempotency=idempotency_key),
            capability="experiments.batch-upsert",
        )

    def get(
        self,
        campaign_id: UUID | str,
        experiment_id: UUID | str,
    ) -> ExperimentResponse:
        """Retrieve one complete experiment.

        Args:
            campaign_id: Public campaign UUID.
            experiment_id: Public experiment UUID.

        Returns:
            Typed experiment representation.

        """
        return self.get_with_metadata(campaign_id, experiment_id).data

    def get_with_metadata(
        self,
        campaign_id: UUID | str,
        experiment_id: UUID | str,
    ) -> ApiResponse[ExperimentResponse]:
        """Retrieve an experiment plus its ETag and correlation metadata.

        Args:
            campaign_id: Public campaign UUID.
            experiment_id: Public experiment UUID.

        Returns:
            Typed experiment response with safe HTTP metadata.

        """
        response = self._response(
            "getExperiment",
            ExperimentResponse,
            path_values=self._ids(campaign_id, experiment_id),
        )
        if response is None:
            raise ResponseValidationError(
                "Unexpected not-modified experiment response",
                operation_id="getExperiment",
            )
        return response

    def patch(
        self,
        campaign_id: UUID | str,
        experiment_id: UUID | str,
        request: ExperimentPatchRequest,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> ExperimentResponse:
        """Apply an optimistic partial experiment update without training.

        Args:
            campaign_id: Public campaign UUID.
            experiment_id: Public experiment UUID.
            request: Validated partial update.
            if_match: Current strong experiment ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Updated experiment.

        """
        return self._model(
            "patchExperiment",
            ExperimentResponse,
            path_values=self._ids(campaign_id, experiment_id),
            body=request,
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

    def delete(
        self,
        campaign_id: UUID | str,
        experiment_id: UUID | str,
        *,
        if_match: str,
        idempotency_key: str | None = None,
    ) -> ExperimentDeleteResponse:
        """Delete an experiment without scheduling training.

        Args:
            campaign_id: Public campaign UUID.
            experiment_id: Public experiment UUID.
            if_match: Current strong experiment ETag.
            idempotency_key: Optional logical mutation key.

        Returns:
            Stable typed deletion tombstone.

        """
        return self._model(
            "deleteExperiment",
            ExperimentDeleteResponse,
            path_values=self._ids(campaign_id, experiment_id),
            headers=mutation_headers(
                idempotency=idempotency_key,
                if_match=if_match,
            ),
        )

    @staticmethod
    def _ids(campaign_id: UUID | str, experiment_id: UUID | str) -> dict[str, str]:
        """Normalize experiment-detail path identifiers.

        Args:
            campaign_id: Public campaign UUID.
            experiment_id: Public experiment UUID.

        Returns:
            Validated path-value mapping.

        """
        return {
            "campaign_id": public_id(campaign_id, label="campaign_id"),
            "experiment_id": public_id(experiment_id, label="experiment_id"),
        }

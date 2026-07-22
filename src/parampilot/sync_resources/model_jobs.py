"""Synchronous model-job reads, observations, results, and cancellation."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal
from uuid import UUID

from pydantic import TypeAdapter

from parampilot.models import (
    EmptyJobRequest,
    ModelJobObservationPageResponse,
    ModelJobPageResponse,
    ModelJobResponse,
    PublicModelJobObservation,
)
from parampilot.pagination import iterate_cursor_sync
from parampilot.resources.headers import mutation_headers
from parampilot.serialization import page_limit, public_id
from parampilot.sync_resources.model_job_submissions import (
    SyncModelJobSubmissionMethods,
)
from parampilot.types import JobResult

JobKind = Literal["train", "ask", "predict"]
JobStatus = Literal["planned", "queued", "running", "done", "failed", "canceled"]
JOB_RESULT_ADAPTER: TypeAdapter[JobResult] = TypeAdapter(JobResult)


class SyncModelJobsResource(SyncModelJobSubmissionMethods):
    """Typed synchronous model-job and observation resource."""

    def list(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
        cursor: str | None = None,
        kind: JobKind | None = None,
        status: JobStatus | None = None,
    ) -> ModelJobPageResponse:
        """Fetch one bounded filtered model-job page.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.
            cursor: Opaque continuation cursor.
            kind: Optional closed Train/Ask/Predict filter.
            status: Optional closed job-lifecycle filter.

        Returns:
            Typed model-job page.

        """
        return self._model(
            "listModelJobs",
            ModelJobPageResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={
                "limit": page_limit(limit),
                "cursor": cursor,
                "kind": kind,
                "status": status,
            },
            capability="jobs.explicit-training",
        )

    def iterate(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
        kind: JobKind | None = None,
        status: JobStatus | None = None,
    ) -> Iterator[ModelJobResponse]:
        """Lazily iterate model jobs with stable bounded filters.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.
            kind: Optional closed Train/Ask/Predict filter.
            status: Optional closed job-lifecycle filter.

        Returns:
            Lazy synchronous job iterator.

        """

        def fetch(cursor: str | None) -> ModelJobPageResponse:
            """Fetch one job page.

            Args:
                cursor: Opaque continuation cursor.

            Returns:
                Typed model-job page.

            """
            return self.list(
                campaign_id,
                limit=limit,
                cursor=cursor,
                kind=kind,
                status=status,
            )

        return iterate_cursor_sync(fetch, operation_id="listModelJobs")

    def get(
        self,
        campaign_id: UUID | str,
        job_id: UUID | str,
    ) -> ModelJobResponse:
        """Retrieve one authorized model job.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.

        Returns:
            Typed job representation.

        """
        return self._model(
            "getModelJob",
            ModelJobResponse,
            path_values=self._ids(campaign_id, job_id),
            capability="jobs.explicit-training",
        )

    def get_observation(
        self,
        campaign_id: UUID | str,
        job_id: UUID | str,
    ) -> PublicModelJobObservation:
        """Retrieve the current lean observation for one model job.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.

        Returns:
            Typed privacy-safe job observation.

        """
        return self.get_observation_with_metadata(campaign_id, job_id).data

    def list_observations(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> ModelJobObservationPageResponse:
        """Fetch one bounded campaign observation page.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.
            cursor: Opaque continuation cursor.

        Returns:
            Typed observation page.

        """
        return self._model(
            "listModelJobObservations",
            ModelJobObservationPageResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            params={"limit": page_limit(limit), "cursor": cursor},
            capability="jobs.observations",
        )

    def iterate_observations(
        self,
        campaign_id: UUID | str,
        *,
        limit: int = 100,
    ) -> Iterator[PublicModelJobObservation]:
        """Lazily iterate lean campaign job observations.

        Args:
            campaign_id: Public campaign UUID.
            limit: Page size from 1 through 500.

        Returns:
            Lazy synchronous observation iterator.

        """

        def fetch(cursor: str | None) -> ModelJobObservationPageResponse:
            """Fetch one observation page.

            Args:
                cursor: Opaque continuation cursor.

            Returns:
                Typed observation page.

            """
            return self.list_observations(
                campaign_id,
                limit=limit,
                cursor=cursor,
            )

        return iterate_cursor_sync(fetch, operation_id="listModelJobObservations")

    def cancel(
        self,
        campaign_id: UUID | str,
        job_id: UUID | str,
        *,
        idempotency_key: str | None = None,
    ) -> ModelJobResponse:
        """Request cancellation through the locked job lifecycle transition.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.
            idempotency_key: Optional logical cancellation key.

        Returns:
            Updated job representation.

        """
        return self._model(
            "cancelModelJob",
            ModelJobResponse,
            path_values=self._ids(campaign_id, job_id),
            body=EmptyJobRequest(),
            headers=mutation_headers(idempotency=idempotency_key),
            capability="jobs.explicit-training",
        )

    def get_result(
        self,
        campaign_id: UUID | str,
        job_id: UUID | str,
    ) -> JobResult:
        """Retrieve one concrete Train, Ask, or Predict terminal result.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.

        Returns:
            Concrete discriminated terminal result.

        """
        return self._model(
            "getModelJobResult",
            JOB_RESULT_ADAPTER,
            path_values=self._ids(campaign_id, job_id),
            capability="jobs.explicit-training",
        )

    @staticmethod
    def _ids(campaign_id: UUID | str, job_id: UUID | str) -> dict[str, str]:
        """Normalize job-detail path identifiers.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.

        Returns:
            Validated path-value mapping.

        """
        return {
            "campaign_id": public_id(campaign_id, label="campaign_id"),
            "job_id": public_id(job_id, label="job_id"),
        }

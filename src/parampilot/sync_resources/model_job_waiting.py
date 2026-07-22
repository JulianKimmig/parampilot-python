"""Synchronous observation metadata, typed handles, and job waiting."""

from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter

from parampilot.errors import ResponseValidationError
from parampilot.job_handles import AnyJobHandle, job_handle
from parampilot.job_waiting import ProgressCallback, SyncJobWaiter
from parampilot.models import (
    EmptyJobRequest,
    ModelJobResponse,
    PublicModelJobObservation,
)
from parampilot.resources.headers import mutation_headers
from parampilot.responses import ApiResponse
from parampilot.serialization import public_id
from parampilot.sync_resources.base import SyncResource
from parampilot.types import JobResult

JOB_RESULT_ADAPTER: TypeAdapter[JobResult] = TypeAdapter(JobResult)


class SyncModelJobWaitingMethods(SyncResource):
    """Sync waiting and handle methods mixed into the model-job resource."""

    def get_observation_with_metadata(
        self,
        campaign_id: UUID | str,
        job_id: UUID | str,
    ) -> ApiResponse[PublicModelJobObservation]:
        """Retrieve one observation plus safe polling/correlation metadata.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.

        Returns:
            Validated observation with safe response headers.

        """
        response = self._response(
            "getModelJobObservation",
            PublicModelJobObservation,
            path_values=self._wait_ids(campaign_id, job_id),
            capability="jobs.observations",
        )
        if response is None:
            raise ResponseValidationError(
                "Unexpected not-modified model-job observation",
                operation_id="getModelJobObservation",
            )
        return response

    def wait(
        self,
        campaign_id: UUID | str,
        job_id: UUID | str,
        *,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: ProgressCallback | None = None,
        cancel_remote: bool = False,
        cancel_idempotency_key: str | None = None,
    ) -> JobResult:
        """Block for an existing job's concrete terminal result.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.
            timeout: Positive local timeout or ``None``.
            poll_interval: Client minimum seconds between observations.
            on_progress: Optional validated significant-change callback.
            cancel_remote: Explicitly cancel if local waiting terminates.
            cancel_idempotency_key: Optional logical key for explicit cancellation.

        Returns:
            Concrete Train, Ask, or Predict terminal result.

        """
        ids = self._wait_ids(campaign_id, job_id)

        def fetch() -> ApiResponse[PublicModelJobObservation]:
            """Fetch one current typed observation with safe metadata.

            Returns:
                Current model-job observation response.

            """
            return self.get_observation_with_metadata(campaign_id, job_id)

        def result() -> JobResult:
            """Fetch the concrete terminal result.

            Returns:
                Concrete Train, Ask, or Predict result.

            """
            return self._model(
                "getModelJobResult",
                JOB_RESULT_ADAPTER,
                path_values=ids,
                capability="jobs.explicit-training",
            )

        def cancel() -> ModelJobResponse:
            """Explicitly request remote cancellation.

            Returns:
                Updated public model-job response.

            """
            return self._model(
                "cancelModelJob",
                ModelJobResponse,
                path_values=ids,
                body=EmptyJobRequest(),
                headers=mutation_headers(idempotency=cancel_idempotency_key),
                capability="jobs.explicit-training",
            )

        return SyncJobWaiter().wait(
            campaign_id=campaign_id,
            job_id=job_id,
            fetch=fetch,
            result=result,
            cancel=cancel,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=on_progress,
            cancel_remote=cancel_remote,
        )

    @staticmethod
    def handle(job: ModelJobResponse) -> AnyJobHandle:
        """Convert a public job response into a reconstructable typed handle.

        Args:
            job: Validated submitted or retrieved model job.

        Returns:
            Concrete Train, Ask, or Predict pure-data handle.

        """
        return job_handle(job)

    @staticmethod
    def _wait_ids(campaign_id: UUID | str, job_id: UUID | str) -> dict[str, str]:
        """Normalize job-detail path identifiers for waiting operations.

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

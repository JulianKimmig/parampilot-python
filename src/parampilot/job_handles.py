"""Reconstructable typed job handles without clients, tokens, or private paths."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Literal, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from parampilot.job_waiting.callbacks import AsyncProgressCallback, ProgressCallback
from parampilot.job_waiting.validation import validate_result_kind
from parampilot.models import (
    AskResult,
    ModelJobResponse,
    PredictResult,
    PublicModelJobObservation,
    TrainResult,
)
from parampilot.types import JobResult

if TYPE_CHECKING:
    from parampilot.client.async_client import AsyncParamPilot
    from parampilot.client.sync_client import ParamPilot

ResultT = TypeVar("ResultT", bound=JobResult)
HandleT = TypeVar("HandleT", bound="JobHandle[JobResult]")


class JobHandle(BaseModel, Generic[ResultT]):
    """Pure-data reference feeding either native client modality.

    Args:
        campaign_id: Public campaign UUID containing the job.
        job_id: Public model-job UUID.
        kind: Train, Ask, or Predict result discriminator.

    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    campaign_id: UUID
    job_id: UUID
    kind: Literal["train", "ask", "predict"]

    @classmethod
    def from_job(cls: type[HandleT], job: ModelJobResponse) -> HandleT:
        """Reconstruct a handle from a submitted public job response.

        Args:
            job: Validated submitted or retrieved model job.

        Returns:
            Concrete handle validated against its declared kind.

        """
        return cls(
            campaign_id=job.campaign_id,
            job_id=job.id,
            kind=job.kind.value,
        )

    def refresh(self, client: ParamPilot) -> PublicModelJobObservation:
        """Fetch the current observation through a sync client.

        Args:
            client: Open native synchronous SDK client.

        Returns:
            Validated current observation.

        """
        return client.model_jobs.get_observation(self.campaign_id, self.job_id)

    async def refresh_async(
        self,
        client: AsyncParamPilot,
    ) -> PublicModelJobObservation:
        """Fetch the current observation through an async client.

        Args:
            client: Open native asynchronous SDK client.

        Returns:
            Validated current observation.

        """
        return await client.model_jobs.get_observation(self.campaign_id, self.job_id)

    def wait(
        self,
        client: ParamPilot,
        *,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: ProgressCallback | None = None,
        cancel_remote: bool = False,
        cancel_idempotency_key: str | None = None,
    ) -> ResultT:
        """Block for this job's concrete terminal result.

        Args:
            client: Open native synchronous SDK client.
            timeout: Positive local timeout or ``None``.
            poll_interval: Client minimum seconds between observations.
            on_progress: Optional validated significant-change callback.
            cancel_remote: Explicitly cancel if local waiting terminates.
            cancel_idempotency_key: Optional logical key for explicit cancellation.

        Returns:
            Concrete result type bound by this handle.

        """
        result = client.model_jobs.wait(
            self.campaign_id,
            self.job_id,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=on_progress,
            cancel_remote=cancel_remote,
            cancel_idempotency_key=cancel_idempotency_key,
        )
        return cast(ResultT, validate_result_kind(result, expected_kind=self.kind))

    async def wait_async(
        self,
        client: AsyncParamPilot,
        *,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: AsyncProgressCallback | None = None,
        cancel_remote: bool = False,
        cancel_idempotency_key: str | None = None,
    ) -> ResultT:
        """Await this job's concrete terminal result.

        Args:
            client: Open native asynchronous SDK client.
            timeout: Positive local timeout or ``None``.
            poll_interval: Client minimum seconds between observations.
            on_progress: Optional sync-or-awaitable validated callback.
            cancel_remote: Explicitly cancel if local waiting terminates.
            cancel_idempotency_key: Optional logical key for explicit cancellation.

        Returns:
            Concrete result type bound by this handle.

        """
        result = await client.model_jobs.wait(
            self.campaign_id,
            self.job_id,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=on_progress,
            cancel_remote=cancel_remote,
            cancel_idempotency_key=cancel_idempotency_key,
        )
        return cast(ResultT, validate_result_kind(result, expected_kind=self.kind))

    def cancel(
        self,
        client: ParamPilot,
        *,
        idempotency_key: str | None = None,
    ) -> ModelJobResponse:
        """Explicitly request remote cancellation through a sync client.

        Args:
            client: Open native synchronous SDK client.
            idempotency_key: Optional logical cancellation key.

        Returns:
            Updated public job response.

        """
        return client.model_jobs.cancel(
            self.campaign_id,
            self.job_id,
            idempotency_key=idempotency_key,
        )

    async def cancel_async(
        self,
        client: AsyncParamPilot,
        *,
        idempotency_key: str | None = None,
    ) -> ModelJobResponse:
        """Explicitly request remote cancellation through an async client.

        Args:
            client: Open native asynchronous SDK client.
            idempotency_key: Optional logical cancellation key.

        Returns:
            Updated public job response.

        """
        return await client.model_jobs.cancel(
            self.campaign_id,
            self.job_id,
            idempotency_key=idempotency_key,
        )

    def result(self, client: ParamPilot) -> ResultT:
        """Fetch the terminal result through a sync client.

        Args:
            client: Open native synchronous SDK client.

        Returns:
            Concrete result type bound by this handle.

        """
        return cast(
            ResultT,
            validate_result_kind(
                client.model_jobs.get_result(self.campaign_id, self.job_id),
                expected_kind=self.kind,
            ),
        )

    async def result_async(self, client: AsyncParamPilot) -> ResultT:
        """Fetch the terminal result through an async client.

        Args:
            client: Open native asynchronous SDK client.

        Returns:
            Concrete result type bound by this handle.

        """
        return cast(
            ResultT,
            validate_result_kind(
                await client.model_jobs.get_result(self.campaign_id, self.job_id),
                expected_kind=self.kind,
            ),
        )


class TrainingJobHandle(JobHandle[TrainResult]):
    """Reconstructable handle whose terminal result is ``TrainResult``."""

    kind: Literal["train"] = "train"


class AskJobHandle(JobHandle[AskResult]):
    """Reconstructable handle whose terminal result is ``AskResult``."""

    kind: Literal["ask"] = "ask"


class PredictJobHandle(JobHandle[PredictResult]):
    """Reconstructable handle whose terminal result is ``PredictResult``."""

    kind: Literal["predict"] = "predict"


AnyJobHandle = TrainingJobHandle | AskJobHandle | PredictJobHandle


def job_handle(job: ModelJobResponse) -> AnyJobHandle:
    """Convert a public job response into its concrete pure-data handle.

    Args:
        job: Validated submitted or retrieved model job.

    Returns:
        Train, Ask, or Predict handle selected by the public discriminator.

    Raises:
        ValueError: If a future server job kind is unsupported by this SDK.

    """
    if job.kind.value == "train":
        return TrainingJobHandle.from_job(job)
    if job.kind.value == "ask":
        return AskJobHandle.from_job(job)
    if job.kind.value == "predict":
        return PredictJobHandle.from_job(job)
    raise ValueError(f"Unsupported ParamPilot model job kind {job.kind.value!r}")


__all__ = [
    "AnyJobHandle",
    "AskJobHandle",
    "JobHandle",
    "PredictJobHandle",
    "TrainingJobHandle",
    "job_handle",
]

"""Explicit synchronous Train, Ask, and Predict job submissions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar
from uuid import UUID

from parampilot.errors import ResponseValidationError
from parampilot.job_waiting import ProgressCallback
from parampilot.job_waiting.validation import validate_wait_timing
from parampilot.models import (
    AskJobRequest,
    AskResult,
    EmptyJobRequest,
    ModelJobResponse,
    PredictionJobRequest,
    PredictResult,
    TrainResult,
)
from parampilot.resources.headers import mutation_headers
from parampilot.serialization import public_id
from parampilot.sync_resources.model_job_waiting import SyncModelJobWaitingMethods

ResultT = TypeVar("ResultT", TrainResult, AskResult, PredictResult)


class SyncModelJobSubmissionMethods(SyncModelJobWaitingMethods):
    """Typed sync submissions with one visibly train-capable method."""

    def train_model(
        self,
        campaign_id: UUID | str,
        *,
        idempotency_key: str | None = None,
        wait: bool = False,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: ProgressCallback | None = None,
        cancel_remote: bool = False,
        cancel_idempotency_key: str | None = None,
    ) -> ModelJobResponse | TrainResult:
        """Explicitly create and queue the sole public training job.

        Args:
            campaign_id: Public campaign UUID.
            idempotency_key: Optional logical job-submission key.
            wait: Block and return the terminal Train result when true.
            timeout: Positive local wait timeout or ``None``.
            poll_interval: Client minimum seconds between observations.
            on_progress: Optional validated significant-change callback.
            cancel_remote: Explicitly cancel if local waiting terminates.
            cancel_idempotency_key: Optional logical cancellation key.

        Returns:
            Accepted queued job, or terminal Train result when waiting.

        """
        return self._submit(
            "createTrainingJob",
            campaign_id,
            EmptyJobRequest(),
            idempotency_key=idempotency_key,
            result_type=TrainResult,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=on_progress,
            cancel_remote=cancel_remote,
            cancel_idempotency_key=cancel_idempotency_key,
        )

    def create_ask_job(
        self,
        campaign_id: UUID | str,
        *,
        n: int,
        idempotency_key: str | None = None,
        wait: bool = False,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: ProgressCallback | None = None,
        cancel_remote: bool = False,
        cancel_idempotency_key: str | None = None,
    ) -> ModelJobResponse | AskResult:
        """Create a candidate-generation job without training.

        Args:
            campaign_id: Public campaign UUID.
            n: Candidate count from 1 through 500.
            idempotency_key: Optional logical job-submission key.
            wait: Block and return the terminal Ask result when true.
            timeout: Positive local wait timeout or ``None``.
            poll_interval: Client minimum seconds between observations.
            on_progress: Optional validated significant-change callback.
            cancel_remote: Explicitly cancel if local waiting terminates.
            cancel_idempotency_key: Optional logical cancellation key.

        Returns:
            Accepted queued job, or terminal Ask result when waiting.

        Raises:
            TrainingRequiredError: If the server model is missing or stale.

        """
        return self._submit(
            "createAskJob",
            campaign_id,
            AskJobRequest(n=n),
            idempotency_key=idempotency_key,
            result_type=AskResult,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=on_progress,
            cancel_remote=cancel_remote,
            cancel_idempotency_key=cancel_idempotency_key,
        )

    def create_prediction_job(
        self,
        campaign_id: UUID | str,
        *,
        rows: Sequence[Mapping[str, Any]],
        idempotency_key: str | None = None,
        wait: bool = False,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: ProgressCallback | None = None,
        cancel_remote: bool = False,
        cancel_idempotency_key: str | None = None,
    ) -> ModelJobResponse | PredictResult:
        """Create an ordered prediction job without training.

        Args:
            campaign_id: Public campaign UUID.
            rows: One through 500 complete campaign-domain input rows.
            idempotency_key: Optional logical job-submission key.
            wait: Block and return the terminal Predict result when true.
            timeout: Positive local wait timeout or ``None``.
            poll_interval: Client minimum seconds between observations.
            on_progress: Optional validated significant-change callback.
            cancel_remote: Explicitly cancel if local waiting terminates.
            cancel_idempotency_key: Optional logical cancellation key.

        Returns:
            Accepted queued job, or terminal Predict result when waiting.

        Raises:
            TrainingRequiredError: If the server model is missing or stale.

        """
        return self._submit(
            "createPredictionJob",
            campaign_id,
            PredictionJobRequest(rows=[dict(row) for row in rows]),
            idempotency_key=idempotency_key,
            result_type=PredictResult,
            wait=wait,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=on_progress,
            cancel_remote=cancel_remote,
            cancel_idempotency_key=cancel_idempotency_key,
        )

    def _submit(
        self,
        operation_id: str,
        campaign_id: UUID | str,
        request: AskJobRequest | PredictionJobRequest | EmptyJobRequest,
        *,
        idempotency_key: str | None,
        result_type: type[ResultT],
        wait: bool,
        timeout: float | None,
        poll_interval: float,
        on_progress: ProgressCallback | None,
        cancel_remote: bool,
        cancel_idempotency_key: str | None,
    ) -> ModelJobResponse | ResultT:
        """Submit one explicit typed model job.

        Args:
            operation_id: Train, Ask, or Predict submission operation ID.
            campaign_id: Public campaign UUID.
            request: Validated discriminated job request body.
            idempotency_key: Optional logical submission key.
            result_type: Expected concrete result model when waiting.
            wait: Whether to block for terminal completion.
            timeout: Positive local wait timeout or ``None``.
            poll_interval: Client minimum seconds between observations.
            on_progress: Optional validated significant-change callback.
            cancel_remote: Explicitly cancel if local waiting terminates.
            cancel_idempotency_key: Optional logical cancellation key.

        Returns:
            Accepted queued job, or expected terminal result when waiting.

        """
        if wait:
            validate_wait_timing(timeout=timeout, poll_interval=poll_interval)
        submitted = self._model(
            operation_id,
            ModelJobResponse,
            path_values={"campaign_id": public_id(campaign_id, label="campaign_id")},
            body=request,
            headers=mutation_headers(idempotency=idempotency_key),
            capability="jobs.explicit-training",
        )
        if not wait:
            return submitted
        result = self.wait(
            submitted.campaign_id,
            submitted.id,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=on_progress,
            cancel_remote=cancel_remote,
            cancel_idempotency_key=cancel_idempotency_key,
        )
        if not isinstance(result, result_type):
            raise ResponseValidationError(
                "The ParamPilot terminal job result kind did not match submission",
                operation_id=operation_id,
            )
        return result

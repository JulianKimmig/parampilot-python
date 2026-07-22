"""Native asynchronous entry points for explicit composite workflows."""

from __future__ import annotations

from uuid import UUID

from parampilot.async_workflow_runtime import AsyncWorkflowRuntime
from parampilot.async_workflow_stages import execute_async_workflow
from parampilot.resources.experiments import ExperimentsResource
from parampilot.resources.model_jobs import ModelJobsResource
from parampilot.workflow_models import (
    AddExperimentsTrainAndAskCheckpoint,
    AddExperimentsTrainAndAskResult,
    AsyncWorkflowProgressCallback,
)
from parampilot.workflow_support import (
    ExperimentInput,
    prepare_new_workflow,
    prepare_resumed_workflow,
)


class AsyncWorkflows:
    """Awaitable composite workflows over existing typed public resources.

    Args:
        experiments: Native asynchronous experiment resource.
        model_jobs: Native asynchronous model-job resource.

    """

    def __init__(
        self,
        experiments: ExperimentsResource,
        model_jobs: ModelJobsResource,
    ) -> None:
        """Bind orchestration to one client's existing resource instances.

        Args:
            experiments: Native asynchronous experiment resource.
            model_jobs: Native asynchronous model-job resource.

        """
        self._experiments = experiments
        self._model_jobs = model_jobs

    async def add_experiments_train_and_ask(
        self,
        campaign_id: UUID | str,
        experiments: ExperimentInput,
        *,
        n: int,
        idempotency_key: str | None = None,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: AsyncWorkflowProgressCallback | None = None,
    ) -> AddExperimentsTrainAndAskResult:
        """Upload experiments, explicitly Train, then Ask in one awaited call.

        Args:
            campaign_id: Public campaign UUID.
            experiments: Typed request or one through 500 experiment rows.
            n: Number of suggested experiments from 1 through 500.
            idempotency_key: Optional stable key for process-loss recovery.
            timeout: Positive local timeout for each job wait or ``None``.
            poll_interval: Client minimum seconds between job observations.
            on_progress: Optional sync-or-awaitable stage-aware callback.

        Returns:
            Completed checkpoint and typed suggested experiments.

        """
        prepared = prepare_new_workflow(
            campaign_id,
            experiments,
            n=n,
            idempotency_key=idempotency_key,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        return await execute_async_workflow(
            AsyncWorkflowRuntime(
                self._experiments,
                self._model_jobs,
                timeout=timeout,
                poll_interval=poll_interval,
                callback=on_progress,
            ),
            prepared,
        )

    async def resume_add_experiments_train_and_ask(
        self,
        checkpoint: AddExperimentsTrainAndAskCheckpoint,
        experiments: ExperimentInput,
        *,
        n: int,
        idempotency_key: str | None = None,
        timeout: float | None = 600.0,
        poll_interval: float = 1.0,
        on_progress: AsyncWorkflowProgressCallback | None = None,
    ) -> AddExperimentsTrainAndAskResult:
        """Resume the explicit workflow without repeating completed Train work.

        Args:
            checkpoint: Serialized recovery state from a prior result/error.
            experiments: Original typed request or experiment rows.
            n: Original number of requested suggestions.
            idempotency_key: Optional original caller workflow key.
            timeout: Positive local timeout for each job wait or ``None``.
            poll_interval: Client minimum seconds between job observations.
            on_progress: Optional sync-or-awaitable stage-aware callback.

        Returns:
            Completed checkpoint and typed suggested experiments.

        """
        prepared = prepare_resumed_workflow(
            checkpoint,
            experiments,
            n=n,
            idempotency_key=idempotency_key,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        return await execute_async_workflow(
            AsyncWorkflowRuntime(
                self._experiments,
                self._model_jobs,
                timeout=timeout,
                poll_interval=poll_interval,
                callback=on_progress,
            ),
            prepared,
        )


__all__ = ["AsyncWorkflows"]

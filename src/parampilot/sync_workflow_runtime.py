"""Shared synchronous resource-call and progress boundaries for workflows."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from parampilot.errors import ParamPilotError
from parampilot.models import PublicModelJobObservation
from parampilot.sync_resources.experiments import SyncExperimentsResource
from parampilot.sync_resources.model_jobs import SyncModelJobsResource
from parampilot.workflow_errors import (
    AddExperimentsTrainAndAskError,
    WorkflowProgressCallbackError,
)
from parampilot.workflow_models import (
    AddExperimentsTrainAndAskCheckpoint,
    WorkflowEventStatus,
    WorkflowPhase,
    WorkflowProgressCallback,
    WorkflowProgressEvent,
)

ResultT = TypeVar("ResultT")


class SyncWorkflowRuntime:
    """Bound resources, wait controls, error policy, and progress delivery.

    Args:
        experiments: Native synchronous experiment resource.
        model_jobs: Native synchronous model-job resource.
        timeout: Positive per-job wait timeout or ``None``.
        poll_interval: Client minimum observation interval.
        callback: Optional validated stage-aware progress callback.

    """

    def __init__(
        self,
        experiments: SyncExperimentsResource,
        model_jobs: SyncModelJobsResource,
        *,
        timeout: float | None,
        poll_interval: float,
        callback: WorkflowProgressCallback | None,
    ) -> None:
        """Store one workflow invocation's native boundaries.

        Args:
            experiments: Native synchronous experiment resource.
            model_jobs: Native synchronous model-job resource.
            timeout: Positive per-job wait timeout or ``None``.
            poll_interval: Client minimum observation interval.
            callback: Optional validated stage-aware progress callback.

        """
        self.experiments = experiments
        self.model_jobs = model_jobs
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.callback = callback

    def call(
        self,
        action: Callable[[], ResultT],
        checkpoint: AddExperimentsTrainAndAskCheckpoint,
        phase: WorkflowPhase,
    ) -> ResultT:
        """Run one resource call and attach its safe recovery checkpoint.

        Args:
            action: Zero-argument typed resource operation.
            checkpoint: Last durably completed stage.
            phase: Visible workflow phase performing the call.

        Returns:
            Typed resource operation result.

        Raises:
            AddExperimentsTrainAndAskError: With checkpoint on SDK failure.
            WorkflowProgressCallbackError: For nested waiter callback failure.

        """
        try:
            return action()
        except ParamPilotError as error:
            callback_error = error.__cause__
            if isinstance(callback_error, WorkflowProgressCallbackError):
                raise callback_error from error
            raise self.failure(checkpoint, phase) from error

    def emit(
        self,
        phase: WorkflowPhase,
        checkpoint: AddExperimentsTrainAndAskCheckpoint,
        *,
        started: bool = False,
        observation: PublicModelJobObservation | None = None,
    ) -> None:
        """Deliver one validated event and type caller callback failures.

        Args:
            phase: Visible workflow phase.
            checkpoint: Last durably completed stage.
            started: Mark a phase-start event when true.
            observation: Optional validated job progress observation.

        Raises:
            WorkflowProgressCallbackError: If caller progress code fails.

        """
        if self.callback is None:
            return
        event = WorkflowProgressEvent(
            phase=phase,
            status=(
                WorkflowEventStatus.started
                if started
                else (
                    WorkflowEventStatus.progress
                    if observation is not None
                    else WorkflowEventStatus.completed
                )
            ),
            checkpoint=checkpoint,
            observation=observation,
        )
        try:
            self.callback(event)
        except Exception as error:
            raise WorkflowProgressCallbackError(
                "The explicit workflow progress callback failed",
                checkpoint=checkpoint,
                failed_phase=phase,
            ) from error

    @staticmethod
    def failure(
        checkpoint: AddExperimentsTrainAndAskCheckpoint,
        phase: WorkflowPhase,
    ) -> AddExperimentsTrainAndAskError:
        """Build one privacy-safe recoverable stage failure.

        Args:
            checkpoint: Last durably completed stage.
            phase: Visible phase that failed.

        Returns:
            Typed recoverable workflow failure.

        """
        return AddExperimentsTrainAndAskError(
            f"The explicit upload-Train-Ask workflow failed during {phase.value}",
            checkpoint=checkpoint,
            failed_phase=phase,
        )


__all__ = ["SyncWorkflowRuntime"]

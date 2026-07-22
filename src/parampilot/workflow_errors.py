"""Recoverable public errors for explicit train-named composite workflows."""

from __future__ import annotations

from parampilot.errors import WorkflowError
from parampilot.workflow_models import (
    AddExperimentsTrainAndAskCheckpoint,
    WorkflowPhase,
)


class AddExperimentsTrainAndAskError(WorkflowError):
    """Failure with the safe checkpoint needed to inspect or resume work.

    Args:
        message: Privacy-safe workflow diagnostic.
        checkpoint: Last durably completed workflow stage.
        failed_phase: Visible phase that could not complete.

    """

    def __init__(
        self,
        message: str,
        *,
        checkpoint: AddExperimentsTrainAndAskCheckpoint,
        failed_phase: WorkflowPhase,
    ) -> None:
        """Initialize a recoverable explicit-training workflow failure.

        Args:
            message: Privacy-safe workflow diagnostic.
            checkpoint: Last durably completed workflow stage.
            failed_phase: Visible phase that could not complete.

        """
        self.checkpoint = checkpoint
        self.failed_phase = failed_phase
        super().__init__(message)


class WorkflowResumeMismatchError(AddExperimentsTrainAndAskError):
    """Raised before HTTP when resume inputs do not match the checkpoint."""


class WorkflowProgressCallbackError(AddExperimentsTrainAndAskError):
    """Wrap caller progress-code failure without retry or remote cancellation."""


__all__ = [
    "AddExperimentsTrainAndAskError",
    "WorkflowProgressCallbackError",
    "WorkflowResumeMismatchError",
]

"""Strict public values for explicit multi-operation workflow recovery."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from parampilot.models import (
    AskResult,
    ExperimentBatchResponse,
    ExperimentResponse,
    PublicModelJobObservation,
    TrainResult,
)


class WorkflowStage(str, Enum):
    """Last durably completed stage of upload, Train, Ask, and retrieval."""

    initialized = "initialized"
    experiments_upserted = "experiments_upserted"
    training_submitted = "training_submitted"
    training_completed = "training_completed"
    ask_submitted = "ask_submitted"
    ask_completed = "ask_completed"
    completed = "completed"


class WorkflowPhase(str, Enum):
    """Visible operation phase used by progress and recovery errors."""

    validation = "validation"
    upload = "upload"
    training = "training"
    ask = "ask"
    suggestions = "suggestions"
    terminal = "terminal"


class WorkflowEventStatus(str, Enum):
    """Lifecycle status of one workflow progress delivery."""

    started = "started"
    progress = "progress"
    completed = "completed"


STAGE_RANK = {stage: index for index, stage in enumerate(WorkflowStage)}


def stage_at_least(current: WorkflowStage, target: WorkflowStage) -> bool:
    """Return whether a checkpoint has completed ``target`` or a later stage.

    Args:
        current: Current durable checkpoint stage.
        target: Stage being tested.

    Returns:
        Whether ``current`` ranks at or after ``target``.

    """
    return STAGE_RANK[current] >= STAGE_RANK[target]


class WorkflowIdempotencyKeys(BaseModel):
    """Operation-specific deterministic subkeys for safe workflow replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiments: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")
    training: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")
    training_cancel: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")
    ask: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")
    ask_cancel: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")


class AddExperimentsTrainAndAskCheckpoint(BaseModel):
    """Token-free restart state for the explicit upload/Train/Ask workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    campaign_id: UUID
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_count: int = Field(ge=1, le=500)
    requested_suggestions: int = Field(ge=1, le=500)
    stage: WorkflowStage = WorkflowStage.initialized
    idempotency_keys: WorkflowIdempotencyKeys
    batch_result: ExperimentBatchResponse | None = None
    training_job_id: UUID | None = None
    training_result: TrainResult | None = None
    ask_job_id: UUID | None = None
    ask_result: AskResult | None = None

    @model_validator(mode="after")
    def validate_stage_data(self) -> AddExperimentsTrainAndAskCheckpoint:
        """Require exactly the recovery data implied by the durable stage.

        Returns:
            Validated checkpoint.

        Raises:
            ValueError: If required stage data is missing or premature.

        """
        requirements = (
            (WorkflowStage.experiments_upserted, "batch_result"),
            (WorkflowStage.training_submitted, "training_job_id"),
            (WorkflowStage.training_completed, "training_result"),
            (WorkflowStage.ask_submitted, "ask_job_id"),
            (WorkflowStage.ask_completed, "ask_result"),
        )
        for required_stage, field_name in requirements:
            value = getattr(self, field_name)
            required = stage_at_least(self.stage, required_stage)
            if required and value is None:
                raise ValueError(
                    f"{field_name} is required from stage {required_stage.value}"
                )
            if not required and value is not None:
                raise ValueError(
                    f"{field_name} is not valid before stage {required_stage.value}"
                )
        return self


class WorkflowProgressEvent(BaseModel):
    """Validated stage-aware progress snapshot for caller presentation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: WorkflowPhase
    status: WorkflowEventStatus
    checkpoint: AddExperimentsTrainAndAskCheckpoint
    observation: PublicModelJobObservation | None = None


WorkflowProgressCallback = Callable[[WorkflowProgressEvent], None]
AsyncWorkflowProgressCallback = Callable[
    [WorkflowProgressEvent],
    None | Awaitable[None],
]


class AddExperimentsTrainAndAskResult(BaseModel):
    """Completed checkpoint plus Ask-created experiments in requested order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint: AddExperimentsTrainAndAskCheckpoint
    suggested_experiments: list[ExperimentResponse] = Field(
        min_length=1, max_length=500
    )

    @model_validator(mode="after")
    def validate_completed_result(self) -> AddExperimentsTrainAndAskResult:
        """Bind suggestions to the completed Ask result and requested count.

        Returns:
            Validated completed workflow result.

        Raises:
            ValueError: If checkpoint or ordered suggestions are inconsistent.

        """
        if self.checkpoint.stage is not WorkflowStage.completed:
            raise ValueError("workflow result requires a completed checkpoint")
        ask_result = self.checkpoint.ask_result
        if ask_result is None:
            raise ValueError("workflow result requires an Ask result")
        actual_ids = [item.id for item in self.suggested_experiments]
        if actual_ids != ask_result.created_experiment_ids:
            raise ValueError("suggested experiments must preserve Ask result order")
        if len(actual_ids) != self.checkpoint.requested_suggestions:
            raise ValueError("suggestion count must match the workflow request")
        return self


__all__ = [
    "AddExperimentsTrainAndAskCheckpoint",
    "AddExperimentsTrainAndAskResult",
    "AsyncWorkflowProgressCallback",
    "WorkflowEventStatus",
    "WorkflowIdempotencyKeys",
    "WorkflowPhase",
    "WorkflowProgressCallback",
    "WorkflowProgressEvent",
    "WorkflowStage",
    "stage_at_least",
]

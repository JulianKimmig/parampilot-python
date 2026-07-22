"""Asynchronous durable stages for the explicit upload-Train-Ask workflow."""

from __future__ import annotations

from parampilot.async_workflow_runtime import AsyncWorkflowRuntime
from parampilot.errors import ParamPilotError, ResponseValidationError
from parampilot.models import (
    AskResult,
    ExperimentResponse,
    ModelJobResponse,
    PublicModelJobObservation,
    TrainResult,
)
from parampilot.workflow_models import (
    AddExperimentsTrainAndAskCheckpoint,
    AddExperimentsTrainAndAskResult,
    WorkflowPhase,
    WorkflowStage,
    stage_at_least,
)
from parampilot.workflow_support import (
    PreparedWorkflow,
    advance_checkpoint,
    ordered_suggestions,
)


async def execute_async_workflow(
    runtime: AsyncWorkflowRuntime,
    prepared: PreparedWorkflow,
) -> AddExperimentsTrainAndAskResult:
    """Advance all incomplete asynchronous stages in contract order.

    Args:
        runtime: Bound resources, controls, and progress policy.
        prepared: Validated request and new/resumed checkpoint.

    Returns:
        Completed checkpoint and ordered suggested experiments.

    """
    checkpoint = await _upload(runtime, prepared)
    checkpoint = await _train(runtime, checkpoint)
    checkpoint = await _ask(runtime, checkpoint)
    suggestions, checkpoint = await _suggestions(runtime, checkpoint)
    await runtime.emit(WorkflowPhase.terminal, checkpoint)
    return AddExperimentsTrainAndAskResult(
        checkpoint=checkpoint,
        suggested_experiments=suggestions,
    )


async def _upload(
    runtime: AsyncWorkflowRuntime,
    prepared: PreparedWorkflow,
) -> AddExperimentsTrainAndAskCheckpoint:
    """Upsert the atomic batch unless already checkpointed.

    Args:
        runtime: Bound asynchronous workflow runtime.
        prepared: Validated batch request and checkpoint.

    Returns:
        Experiments-upserted or later checkpoint.

    """
    checkpoint = prepared.checkpoint
    if stage_at_least(checkpoint.stage, WorkflowStage.experiments_upserted):
        return checkpoint
    await runtime.emit(WorkflowPhase.upload, checkpoint, started=True)
    batch = await runtime.call(
        lambda: runtime.experiments.batch_upsert(
            checkpoint.campaign_id,
            prepared.experiments,
            idempotency_key=checkpoint.idempotency_keys.experiments,
        ),
        checkpoint,
        WorkflowPhase.upload,
    )
    checkpoint = advance_checkpoint(
        checkpoint,
        WorkflowStage.experiments_upserted,
        batch_result=batch,
    )
    await runtime.emit(WorkflowPhase.upload, checkpoint)
    return checkpoint


async def _train(
    runtime: AsyncWorkflowRuntime,
    checkpoint: AddExperimentsTrainAndAskCheckpoint,
) -> AddExperimentsTrainAndAskCheckpoint:
    """Submit explicit Train once, then await its existing job.

    Args:
        runtime: Bound asynchronous workflow runtime.
        checkpoint: Current durable stage.

    Returns:
        Training-completed or later checkpoint.

    """
    if stage_at_least(checkpoint.stage, WorkflowStage.training_completed):
        return checkpoint
    await runtime.emit(WorkflowPhase.training, checkpoint, started=True)
    if not stage_at_least(checkpoint.stage, WorkflowStage.training_submitted):

        async def submit() -> ModelJobResponse:
            """Submit and validate one explicit Train job.

            Returns:
                Accepted Train job metadata.

            Raises:
                ResponseValidationError: If nonwaiting submission returns a result.

            """
            value = await runtime.model_jobs.train_model(
                checkpoint.campaign_id,
                idempotency_key=checkpoint.idempotency_keys.training,
            )
            if not isinstance(value, ModelJobResponse):
                raise ResponseValidationError("Train submission returned a result")
            return value

        job = await runtime.call(submit, checkpoint, WorkflowPhase.training)
        checkpoint = advance_checkpoint(
            checkpoint,
            WorkflowStage.training_submitted,
            training_job_id=job.id,
        )

    async def progress(value: PublicModelJobObservation) -> None:
        """Forward one validated Train observation as workflow progress.

        Args:
            value: Validated job observation.

        """
        await runtime.emit(
            WorkflowPhase.training,
            checkpoint,
            observation=value,
        )

    result = await runtime.call(
        lambda: runtime.model_jobs.wait(
            checkpoint.campaign_id,
            checkpoint.training_job_id,  # type: ignore[arg-type]
            timeout=runtime.timeout,
            poll_interval=runtime.poll_interval,
            on_progress=progress,
            cancel_remote=False,
        ),
        checkpoint,
        WorkflowPhase.training,
    )
    if not isinstance(result, TrainResult):
        error = ResponseValidationError("Train job returned another result kind")
        raise runtime.failure(checkpoint, WorkflowPhase.training) from error
    checkpoint = advance_checkpoint(
        checkpoint,
        WorkflowStage.training_completed,
        training_result=result,
    )
    await runtime.emit(WorkflowPhase.training, checkpoint)
    return checkpoint


async def _ask(
    runtime: AsyncWorkflowRuntime,
    checkpoint: AddExperimentsTrainAndAskCheckpoint,
) -> AddExperimentsTrainAndAskCheckpoint:
    """Submit non-training Ask once, then await its existing job.

    Args:
        runtime: Bound asynchronous workflow runtime.
        checkpoint: Current durable stage.

    Returns:
        Ask-completed or later checkpoint.

    """
    if stage_at_least(checkpoint.stage, WorkflowStage.ask_completed):
        return checkpoint
    await runtime.emit(WorkflowPhase.ask, checkpoint, started=True)
    if not stage_at_least(checkpoint.stage, WorkflowStage.ask_submitted):

        async def submit() -> ModelJobResponse:
            """Submit and validate one non-training Ask job.

            Returns:
                Accepted Ask job metadata.

            Raises:
                ResponseValidationError: If nonwaiting submission returns a result.

            """
            value = await runtime.model_jobs.create_ask_job(
                checkpoint.campaign_id,
                n=checkpoint.requested_suggestions,
                idempotency_key=checkpoint.idempotency_keys.ask,
            )
            if not isinstance(value, ModelJobResponse):
                raise ResponseValidationError("Ask submission returned a result")
            return value

        job = await runtime.call(submit, checkpoint, WorkflowPhase.ask)
        checkpoint = advance_checkpoint(
            checkpoint,
            WorkflowStage.ask_submitted,
            ask_job_id=job.id,
        )

    async def progress(value: PublicModelJobObservation) -> None:
        """Forward one validated Ask observation as workflow progress.

        Args:
            value: Validated job observation.

        """
        await runtime.emit(WorkflowPhase.ask, checkpoint, observation=value)

    result = await runtime.call(
        lambda: runtime.model_jobs.wait(
            checkpoint.campaign_id,
            checkpoint.ask_job_id,  # type: ignore[arg-type]
            timeout=runtime.timeout,
            poll_interval=runtime.poll_interval,
            on_progress=progress,
            cancel_remote=False,
        ),
        checkpoint,
        WorkflowPhase.ask,
    )
    if not isinstance(result, AskResult):
        error = ResponseValidationError("Ask job returned another result kind")
        raise runtime.failure(checkpoint, WorkflowPhase.ask) from error
    checkpoint = advance_checkpoint(
        checkpoint,
        WorkflowStage.ask_completed,
        ask_result=result,
    )
    await runtime.emit(WorkflowPhase.ask, checkpoint)
    return checkpoint


async def _suggestions(
    runtime: AsyncWorkflowRuntime,
    checkpoint: AddExperimentsTrainAndAskCheckpoint,
) -> tuple[list[ExperimentResponse], AddExperimentsTrainAndAskCheckpoint]:
    """Fetch and order complete Ask-created experiment resources.

    Args:
        runtime: Bound asynchronous workflow runtime.
        checkpoint: Ask-completed checkpoint.

    Returns:
        Ordered suggestions and completed checkpoint.

    """
    await runtime.emit(WorkflowPhase.suggestions, checkpoint, started=True)
    ask_result = checkpoint.ask_result
    if ask_result is None:
        error = ResponseValidationError("Ask result missing from checkpoint")
        raise runtime.failure(checkpoint, WorkflowPhase.suggestions) from error
    page = await runtime.call(
        lambda: runtime.experiments.list(
            checkpoint.campaign_id,
            limit=len(ask_result.created_experiment_ids),
            ids=ask_result.created_experiment_ids,
        ),
        checkpoint,
        WorkflowPhase.suggestions,
    )
    try:
        suggestions = ordered_suggestions(page, checkpoint)
    except ParamPilotError as error:
        raise runtime.failure(checkpoint, WorkflowPhase.suggestions) from error
    checkpoint = advance_checkpoint(checkpoint, WorkflowStage.completed)
    await runtime.emit(WorkflowPhase.suggestions, checkpoint)
    return suggestions, checkpoint


__all__ = ["execute_async_workflow"]

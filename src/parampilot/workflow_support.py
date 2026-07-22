"""Transport-neutral validation, fingerprint, checkpoint, and ordering helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias
from uuid import UUID

from parampilot.errors import ConfigurationError, ResponseValidationError
from parampilot.job_waiting.validation import validate_wait_timing
from parampilot.models import (
    AskJobRequest,
    ExperimentBatchUpsertItem,
    ExperimentBatchUpsertRequest,
    ExperimentPageResponse,
    ExperimentResponse,
)
from parampilot.serialization import idempotency_key as validated_idempotency_key
from parampilot.serialization import public_id
from parampilot.workflow_errors import WorkflowResumeMismatchError
from parampilot.workflow_models import (
    AddExperimentsTrainAndAskCheckpoint,
    WorkflowIdempotencyKeys,
    WorkflowPhase,
    WorkflowStage,
)

ExperimentInput: TypeAlias = (
    ExperimentBatchUpsertRequest
    | Sequence[ExperimentBatchUpsertItem | Mapping[str, object]]
)


@dataclass(frozen=True, slots=True)
class PreparedWorkflow:
    """Locally validated workflow request and matching recovery checkpoint.

    Args:
        experiments: Typed atomic batch request.
        checkpoint: New or validated resume checkpoint.

    """

    experiments: ExperimentBatchUpsertRequest
    checkpoint: AddExperimentsTrainAndAskCheckpoint


def prepare_new_workflow(
    campaign_id: UUID | str,
    experiments: ExperimentInput,
    *,
    n: int,
    idempotency_key: str | None,
    timeout: float | None,
    poll_interval: float,
) -> PreparedWorkflow:
    """Validate all local inputs and create deterministic stage subkeys.

    Args:
        campaign_id: Public campaign UUID.
        experiments: Typed request or one through 500 row values.
        n: Number of Ask suggestions from 1 through 500.
        idempotency_key: Optional stable caller workflow key.
        timeout: Positive per-job wait timeout or ``None``.
        poll_interval: Client minimum observation interval.

    Returns:
        Prepared request and initialized token-free checkpoint.

    """
    normalized_id, request, ask_request, fingerprint = _validated_inputs(
        campaign_id,
        experiments,
        n=n,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    base_key = validated_idempotency_key(idempotency_key)
    checkpoint = AddExperimentsTrainAndAskCheckpoint(
        campaign_id=normalized_id,
        request_fingerprint=fingerprint,
        experiment_count=len(request.items),
        requested_suggestions=ask_request.n,
        idempotency_keys=derive_workflow_keys(base_key),
    )
    return PreparedWorkflow(experiments=request, checkpoint=checkpoint)


def prepare_resumed_workflow(
    checkpoint: AddExperimentsTrainAndAskCheckpoint,
    experiments: ExperimentInput,
    *,
    n: int,
    idempotency_key: str | None,
    timeout: float | None,
    poll_interval: float,
) -> PreparedWorkflow:
    """Validate restart inputs against a previously serialized checkpoint.

    Args:
        checkpoint: Last safe checkpoint from a prior call.
        experiments: Original typed request or row values.
        n: Original Ask suggestion count.
        idempotency_key: Optional original stable caller workflow key.
        timeout: Positive per-job wait timeout or ``None``.
        poll_interval: Client minimum observation interval.

    Returns:
        Prepared original request and unchanged checkpoint.

    Raises:
        WorkflowResumeMismatchError: Before HTTP if identity or keys differ.

    """
    _, request, ask_request, fingerprint = _validated_inputs(
        checkpoint.campaign_id,
        experiments,
        n=n,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    if fingerprint != checkpoint.request_fingerprint:
        raise WorkflowResumeMismatchError(
            "Workflow resume request fingerprint does not match the checkpoint",
            checkpoint=checkpoint,
            failed_phase=WorkflowPhase.validation,
        )
    if (
        len(request.items) != checkpoint.experiment_count
        or ask_request.n != checkpoint.requested_suggestions
    ):
        raise WorkflowResumeMismatchError(
            "Workflow resume request counts do not match the checkpoint",
            checkpoint=checkpoint,
            failed_phase=WorkflowPhase.validation,
        )
    if idempotency_key is not None:
        resumed_keys = derive_workflow_keys(validated_idempotency_key(idempotency_key))
        if resumed_keys != checkpoint.idempotency_keys:
            raise WorkflowResumeMismatchError(
                "Workflow resume idempotency key does not match the checkpoint",
                checkpoint=checkpoint,
                failed_phase=WorkflowPhase.validation,
            )
    return PreparedWorkflow(experiments=request, checkpoint=checkpoint)


def derive_workflow_keys(base_key: str) -> WorkflowIdempotencyKeys:
    """Derive bounded operation-specific keys without retaining the base key.

    Args:
        base_key: Validated caller or SDK-generated workflow key.

    Returns:
        Deterministic five-operation subkey set.

    """
    digest = hashlib.sha256(base_key.encode("ascii")).hexdigest()
    return WorkflowIdempotencyKeys(
        experiments=f"ppw1.experiments.{digest}",
        training=f"ppw1.training.{digest}",
        training_cancel=f"ppw1.training_cancel.{digest}",
        ask=f"ppw1.ask.{digest}",
        ask_cancel=f"ppw1.ask_cancel.{digest}",
    )


def advance_checkpoint(
    checkpoint: AddExperimentsTrainAndAskCheckpoint,
    stage: WorkflowStage,
    **updates: object,
) -> AddExperimentsTrainAndAskCheckpoint:
    """Build and fully revalidate one immutable forward checkpoint.

    Args:
        checkpoint: Current valid checkpoint.
        stage: Newly completed stage.
        **updates: Recovery fields completed by that stage.

    Returns:
        Revalidated immutable checkpoint.

    """
    values = checkpoint.model_dump(mode="python")
    values.update(updates)
    values["stage"] = stage
    return AddExperimentsTrainAndAskCheckpoint.model_validate(values)


def ordered_suggestions(
    page: ExperimentPageResponse,
    checkpoint: AddExperimentsTrainAndAskCheckpoint,
) -> list[ExperimentResponse]:
    """Validate and order one bounded experiment page by the Ask result IDs.

    Args:
        page: Typed page filtered to Ask-created experiment IDs.
        checkpoint: Ask-completed workflow recovery state.

    Returns:
        Complete suggested experiments in Ask result order.

    Raises:
        ResponseValidationError: If the page is incomplete, duplicated, or extra.

    """
    ask_result = checkpoint.ask_result
    if ask_result is None:
        raise ResponseValidationError(
            "Workflow suggestion retrieval requires an Ask result",
            operation_id="listExperiments",
        )
    expected_ids = ask_result.created_experiment_ids
    if len(expected_ids) != checkpoint.requested_suggestions:
        raise ResponseValidationError(
            "The ParamPilot Ask result count did not match the workflow request",
            operation_id="getModelJobResult",
        )
    by_id = {item.id: item for item in page.items}
    if (
        page.has_more
        or page.next_cursor is not None
        or len(by_id) != len(page.items)
        or set(by_id) != set(expected_ids)
    ):
        raise ResponseValidationError(
            "The ParamPilot suggestion page did not match the Ask result",
            operation_id="listExperiments",
        )
    return [by_id[experiment_id] for experiment_id in expected_ids]


def _validated_inputs(
    campaign_id: UUID | str,
    experiments: ExperimentInput,
    *,
    n: int,
    timeout: float | None,
    poll_interval: float,
) -> tuple[UUID, ExperimentBatchUpsertRequest, AskJobRequest, str]:
    """Normalize every local request input and compute its semantic digest.

    Args:
        campaign_id: Public campaign UUID.
        experiments: Typed request or row sequence.
        n: Ask suggestion count.
        timeout: Positive per-job wait timeout or ``None``.
        poll_interval: Client minimum observation interval.

    Returns:
        Campaign UUID, batch request, Ask request, and SHA-256 fingerprint.

    Raises:
        ConfigurationError: If the request cannot be deterministically encoded.

    """
    normalized_id = UUID(public_id(campaign_id, label="campaign_id"))
    request = (
        experiments
        if isinstance(experiments, ExperimentBatchUpsertRequest)
        else ExperimentBatchUpsertRequest.model_validate({"items": list(experiments)})
    )
    ask_request = AskJobRequest(n=n)
    validate_wait_timing(timeout=timeout, poll_interval=poll_interval)
    try:
        value = {
            "campaign_id": str(normalized_id),
            "experiments": request.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
            "n": ask_request.n,
        }
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            "workflow inputs must have a deterministic JSON representation"
        ) from error
    return (
        normalized_id,
        request,
        ask_request,
        hashlib.sha256(encoded.encode()).hexdigest(),
    )

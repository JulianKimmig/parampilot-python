"""Pure validation, identity, progress, and terminal-state waiter helpers."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from parampilot.errors import (
    AuthenticationError,
    CompatibilityError,
    JobAuthenticationError,
    JobCanceledError,
    JobCompatibilityError,
    JobFailedError,
    JobPollingError,
    JobWaitError,
    ParamPilotError,
)
from parampilot.job_waiting.validation import MAX_POLL_INTERVAL, validate_wait_timing
from parampilot.models import PublicModelJobObservation
from parampilot.responses import ApiResponse
from parampilot.serialization import public_id


@dataclass(frozen=True, slots=True)
class WaitOptions:
    """Validated immutable local waiter controls and public identifiers.

    Args:
        campaign_id: Public campaign UUID.
        job_id: Public model-job UUID.
        timeout: Positive seconds or ``None`` for no local deadline.
        poll_interval: Positive bounded minimum seconds between polls.

    """

    campaign_id: UUID
    job_id: UUID
    timeout: float | None
    poll_interval: float

    @classmethod
    def create(
        cls,
        *,
        campaign_id: UUID | str,
        job_id: UUID | str,
        timeout: float | None,
        poll_interval: float,
    ) -> WaitOptions:
        """Validate public identifiers and local timing controls.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.
            timeout: Positive seconds or ``None``.
            poll_interval: Positive seconds capped at 30.

        Returns:
            Validated waiter options.

        Raises:
            ConfigurationError: If a timing option is nonfinite or out of range.

        """
        validate_wait_timing(timeout=timeout, poll_interval=poll_interval)
        return cls(
            campaign_id=UUID(public_id(campaign_id, label="campaign_id")),
            job_id=UUID(public_id(job_id, label="job_id")),
            timeout=timeout,
            poll_interval=poll_interval,
        )


def progress_fingerprint(observation: PublicModelJobObservation) -> tuple[str, ...]:
    """Build a stable significant-change identity excluding check time.

    Args:
        observation: Validated lean current job observation.

    Returns:
        Hashable lifecycle/progress/liveness/terminal/action identity.

    """
    progress = observation.progress.model_dump_json() if observation.progress else ""
    terminal = (
        observation.terminal_error.model_dump_json()
        if observation.terminal_error
        else ""
    )
    last_contact = (
        observation.liveness.last_contact_at.isoformat()
        if observation.liveness.last_contact_at
        else ""
    )
    return (
        observation.status.value,
        progress,
        observation.liveness.state.value,
        last_contact,
        terminal,
        str(observation.available_actions.can_cancel),
        str(observation.available_actions.can_queue),
    )


def poll_delay(
    response: ApiResponse[PublicModelJobObservation],
    *,
    poll_interval: float,
) -> float:
    """Combine client minimum and numeric server Retry-After guidance.

    Args:
        response: Typed observation plus safe response headers.
        poll_interval: Validated client minimum delay.

    Returns:
        Delay clamped between the client minimum and 30 seconds.

    """
    raw_value = response.headers.get("retry-after")
    if raw_value is None:
        return poll_interval
    try:
        server_delay = float(raw_value)
    except ValueError:
        return poll_interval
    if not isfinite(server_delay) or server_delay < 0:
        return poll_interval
    return min(MAX_POLL_INTERVAL, max(poll_interval, server_delay))


def terminal_error(
    options: WaitOptions,
    observation: PublicModelJobObservation,
) -> JobWaitError | None:
    """Map failed/canceled terminal observations to local typed errors.

    Args:
        options: Validated waiter identity and timing controls.
        observation: Latest validated job observation.

    Returns:
        Terminal error for failed/canceled state, otherwise ``None``.

    """
    if observation.status.value == "failed":
        return JobFailedError(
            "The waited ParamPilot model job failed",
            campaign_id=options.campaign_id,
            job_id=options.job_id,
            last_observation=observation,
        )
    if observation.status.value == "canceled":
        return JobCanceledError(
            "The waited ParamPilot model job was canceled",
            campaign_id=options.campaign_id,
            job_id=options.job_id,
            last_observation=observation,
        )
    return None


def polling_error(
    error: ParamPilotError,
    *,
    options: WaitOptions,
    last_observation: PublicModelJobObservation | None,
    message: str,
) -> JobPollingError:
    """Map a polling/result failure to a recoverable job-specific exception.

    Args:
        error: Typed SDK failure raised by the underlying operation.
        options: Validated waiter identity and timing controls.
        last_observation: Last validated server observation, if any.
        message: Privacy-safe waiting diagnostic.

    Returns:
        Authentication-, compatibility-, or generic polling error.

    """
    error_type: type[JobPollingError]
    if isinstance(error, AuthenticationError):
        error_type = JobAuthenticationError
    elif isinstance(error, CompatibilityError):
        error_type = JobCompatibilityError
    else:
        error_type = JobPollingError
    return error_type(
        message,
        campaign_id=options.campaign_id,
        job_id=options.job_id,
        last_observation=last_observation,
    )

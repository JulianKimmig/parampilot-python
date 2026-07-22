"""Local job-wait controls and concrete-result validation helpers."""

from __future__ import annotations

from math import isfinite
from typing import Literal, TypeVar

from parampilot.errors import ConfigurationError, ResponseValidationError
from parampilot.types import JobResult

MAX_POLL_INTERVAL = 30.0
ResultT = TypeVar("ResultT", bound=JobResult)


def validate_wait_timing(
    *,
    timeout: float | None,
    poll_interval: float,
) -> None:
    """Validate local timing before polling or submitting a waited job.

    Args:
        timeout: Positive local seconds or ``None`` for no deadline.
        poll_interval: Client minimum seconds between observations.

    Raises:
        ConfigurationError: If either control is nonfinite or out of range.

    """
    if timeout is not None and (not isfinite(timeout) or timeout <= 0):
        raise ConfigurationError("timeout must be positive or None")
    if (
        not isfinite(poll_interval)
        or poll_interval < 0.01
        or poll_interval > MAX_POLL_INTERVAL
    ):
        raise ConfigurationError("poll_interval must be from 0.01 to 30 seconds")


def validate_result_kind(
    result: ResultT,
    *,
    expected_kind: Literal["train", "ask", "predict"],
) -> ResultT:
    """Require a terminal result to match its reconstructed handle kind.

    Args:
        result: Validated concrete Train, Ask, or Predict result.
        expected_kind: Result discriminator declared by the handle.

    Returns:
        The unchanged concrete result when its discriminator matches.

    Raises:
        ResponseValidationError: If the result belongs to another job kind.

    """
    if result.kind != expected_kind:
        raise ResponseValidationError(
            "The ParamPilot terminal job result kind did not match its handle",
            operation_id="getModelJobResult",
        )
    return result

"""Deterministic clocks and payloads shared by job-waiter tests."""

from __future__ import annotations

from parampilot.models import PublicModelJobObservation, TrainResult
from parampilot.responses import ApiResponse
from tests.support import job_observation_payload, job_result_payload


class FakeClock:
    """Deterministic monotonic clock with sync and async sleep boundaries."""

    def __init__(self) -> None:
        """Initialize at zero elapsed seconds."""
        self.now = 0.0
        self.delays: list[float] = []

    def monotonic(self) -> float:
        """Return the current deterministic monotonic value.

        Returns:
            Elapsed fake seconds.

        """
        return self.now

    def sleep(self, delay: float) -> None:
        """Advance the deterministic clock synchronously.

        Args:
            delay: Requested nonnegative delay.

        """
        self.delays.append(delay)
        self.now += delay

    async def sleep_async(self, delay: float) -> None:
        """Advance the deterministic clock asynchronously.

        Args:
            delay: Requested nonnegative delay.

        """
        self.sleep(delay)


def _observation(
    status: str,
    *,
    stage: str = "fitting_model",
    retry_after: str | None = None,
) -> ApiResponse[PublicModelJobObservation]:
    """Build one typed observation response with optional poll guidance.

    Args:
        status: Public lifecycle state.
        stage: Canonical running progress stage.
        retry_after: Optional safe Retry-After response value.

    Returns:
        Typed response metadata and observation.

    """
    return ApiResponse(
        data=PublicModelJobObservation.model_validate(
            job_observation_payload(status=status, stage=stage)
        ),
        status_code=200,
        headers={"retry-after": retry_after} if retry_after is not None else {},
        request_id="req-observation",
        etag=None,
    )


def _train_result() -> TrainResult:
    """Build the concrete typed training result.

    Returns:
        Validated terminal Train result.

    """
    return TrainResult.model_validate(job_result_payload(kind="train"))

"""Asynchronous job-wait callback and cancellation state-machine tests."""

from __future__ import annotations

import asyncio

import pytest

from parampilot.job_waiting.async_waiter import AsyncJobWaiter
from parampilot.models import PublicModelJobObservation, TrainResult
from parampilot.responses import ApiResponse
from tests.jobs.waiter_support import FakeClock, _observation, _train_result
from tests.support import CAMPAIGN_ID, JOB_ID


@pytest.mark.asyncio
async def test_async_waiter_supports_awaitable_callbacks_and_terminal_result() -> None:
    """Async polling must await typed callbacks and return the concrete result."""
    clock = FakeClock()
    observations = iter([_observation("running"), _observation("done")])
    delivered: list[str] = []

    async def fetch() -> ApiResponse[PublicModelJobObservation]:
        """Return the next async lifecycle observation.

        Returns:
            Next typed observation response.

        """
        return next(observations)

    async def result() -> TrainResult:
        """Return a typed asynchronous Train result.

        Returns:
            Terminal Train result.

        """
        return _train_result()

    async def callback(value: PublicModelJobObservation) -> None:
        """Record one validated progress delivery.

        Args:
            value: Validated job observation.

        """
        delivered.append(value.status.value)

    waiter = AsyncJobWaiter(
        monotonic=clock.monotonic,
        sleep=clock.sleep_async,
    )

    terminal = await waiter.wait(
        campaign_id=CAMPAIGN_ID,
        job_id=JOB_ID,
        fetch=fetch,
        result=result,
        cancel=lambda: asyncio.sleep(0),
        timeout=10,
        poll_interval=1,
        on_progress=callback,
        cancel_remote=False,
    )

    assert terminal.kind == "train"
    assert delivered == ["running", "done"]


@pytest.mark.asyncio
async def test_async_local_cancellation_never_implies_remote_cancel() -> None:
    """Task cancellation must propagate and leave the remote job untouched."""
    cancel_calls = 0

    async def canceled_sleep(_: float) -> None:
        """Simulate task cancellation at the sleep boundary.

        Raises:
            asyncio.CancelledError: Always.

        """
        raise asyncio.CancelledError

    async def cancel() -> None:
        """Count any unexpected remote cancellation."""
        nonlocal cancel_calls
        cancel_calls += 1

    waiter = AsyncJobWaiter(monotonic=lambda: 0.0, sleep=canceled_sleep)

    with pytest.raises(asyncio.CancelledError):
        await waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=lambda: asyncio.sleep(0, result=_observation("running")),
            result=lambda: asyncio.sleep(0, result=_train_result()),
            cancel=cancel,
            timeout=10,
            poll_interval=1,
            on_progress=None,
            cancel_remote=False,
        )

    assert cancel_calls == 0


@pytest.mark.asyncio
async def test_async_cancellation_can_explicitly_cancel_remote_job() -> None:
    """The explicit async cancel policy must issue exactly one remote cancel."""
    cancel_calls = 0

    async def canceled_sleep(_: float) -> None:
        """Simulate task cancellation at the sleep boundary.

        Raises:
            asyncio.CancelledError: Always.

        """
        raise asyncio.CancelledError

    async def cancel() -> None:
        """Count explicit remote cancellation."""
        nonlocal cancel_calls
        cancel_calls += 1

    waiter = AsyncJobWaiter(monotonic=lambda: 0.0, sleep=canceled_sleep)

    with pytest.raises(asyncio.CancelledError):
        await waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=lambda: asyncio.sleep(0, result=_observation("running")),
            result=lambda: asyncio.sleep(0, result=_train_result()),
            cancel=cancel,
            timeout=10,
            poll_interval=1,
            on_progress=None,
            cancel_remote=True,
        )

    assert cancel_calls == 1

"""Native cancellation-aware asynchronous public model-job polling driver."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from parampilot.errors import (
    JobProgressCallbackError,
    JobWaitTimeoutError,
    ParamPilotError,
)
from parampilot.job_waiting.callbacks import AsyncProgressCallback
from parampilot.job_waiting.state import (
    WaitOptions,
    poll_delay,
    polling_error,
    progress_fingerprint,
    terminal_error,
)
from parampilot.models import PublicModelJobObservation
from parampilot.responses import ApiResponse

ResultT = TypeVar("ResultT")


class AsyncJobWaiter:
    """Await one existing job without hidden submission or remote cancellation.

    Args:
        monotonic: Monotonic seconds source used for local deadlines.
        sleep: Cancellation-aware asynchronous sleep boundary.

    """

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Store deterministic asynchronous time dependencies.

        Args:
            monotonic: Monotonic seconds source used for local deadlines.
            sleep: Cancellation-aware asynchronous sleep boundary.

        """
        self._monotonic = monotonic
        self._sleep = sleep

    async def wait(
        self,
        *,
        campaign_id: UUID | str,
        job_id: UUID | str,
        fetch: Callable[[], Awaitable[ApiResponse[PublicModelJobObservation]]],
        result: Callable[[], Awaitable[ResultT]],
        cancel: Callable[[], Awaitable[object]],
        timeout: float | None,
        poll_interval: float,
        on_progress: AsyncProgressCallback | None,
        cancel_remote: bool,
    ) -> ResultT:
        """Await until an existing job finishes or local waiting terminates.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.
            fetch: Retrieve one typed current observation plus safe metadata.
            result: Retrieve the concrete terminal result.
            cancel: Explicit remote-cancel operation.
            timeout: Positive local timeout or ``None``.
            poll_interval: Client minimum poll interval from 0.01 through 30.
            on_progress: Optional sync-or-awaitable validated callback.
            cancel_remote: Explicitly cancel after a local wait failure.

        Returns:
            Concrete terminal job result.

        Raises:
            JobFailedError: If the remote job reports failed.
            JobCanceledError: If the remote job reports canceled.
            JobWaitTimeoutError: If the local monotonic deadline expires.
            JobPollingError: If a typed polling/result operation fails.
            JobProgressCallbackError: If caller progress code raises.

        """
        options = WaitOptions.create(
            campaign_id=campaign_id,
            job_id=job_id,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        started = self._monotonic()
        last: PublicModelJobObservation | None = None
        last_fingerprint: tuple[str, ...] | None = None
        try:
            while True:
                try:
                    response = await fetch()
                except ParamPilotError as poll_error:
                    if cancel_remote:
                        await cancel()
                    raise polling_error(
                        poll_error,
                        options=options,
                        last_observation=last,
                        message="ParamPilot job polling could not continue",
                    ) from poll_error
                last = response.data
                fingerprint = progress_fingerprint(last)
                if fingerprint != last_fingerprint and on_progress is not None:
                    try:
                        callback_result = on_progress(last)
                        if inspect.isawaitable(callback_result):
                            await callback_result
                    except Exception as error:
                        if cancel_remote:
                            await cancel()
                        raise JobProgressCallbackError(
                            "ParamPilot job progress callback failed",
                            campaign_id=options.campaign_id,
                            job_id=options.job_id,
                            last_observation=last,
                        ) from error
                last_fingerprint = fingerprint
                terminal_failure = terminal_error(options, last)
                if terminal_failure is not None:
                    raise terminal_failure
                if last.status.value == "done":
                    try:
                        return await result()
                    except ParamPilotError as result_error:
                        raise polling_error(
                            result_error,
                            options=options,
                            last_observation=last,
                            message=(
                                "ParamPilot terminal job result could not be retrieved"
                            ),
                        ) from result_error
                elapsed = self._monotonic() - started
                if options.timeout is not None and elapsed >= options.timeout:
                    await self._raise_timeout(options, last, cancel, cancel_remote)
                delay = poll_delay(response, poll_interval=options.poll_interval)
                if options.timeout is not None:
                    delay = min(delay, options.timeout - elapsed)
                await self._sleep(delay)
                if (
                    options.timeout is not None
                    and self._monotonic() - started >= options.timeout
                ):
                    await self._raise_timeout(options, last, cancel, cancel_remote)
        except asyncio.CancelledError:
            if cancel_remote:
                await asyncio.shield(cancel())
            raise

    @staticmethod
    async def _raise_timeout(
        options: WaitOptions,
        last: PublicModelJobObservation | None,
        cancel: Callable[[], Awaitable[object]],
        cancel_remote: bool,
    ) -> None:
        """Optionally cancel remotely and raise a typed local timeout.

        Args:
            options: Validated waiter identity and timing controls.
            last: Last validated observation, if any.
            cancel: Explicit remote-cancel operation.
            cancel_remote: Whether cancellation was explicitly requested.

        Raises:
            JobWaitTimeoutError: Always after optional remote cancellation.

        """
        if cancel_remote:
            await cancel()
        raise JobWaitTimeoutError(
            "ParamPilot job waiting exceeded the local timeout",
            campaign_id=options.campaign_id,
            job_id=options.job_id,
            last_observation=last,
        )

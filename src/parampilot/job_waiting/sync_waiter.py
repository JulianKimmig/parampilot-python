"""Native blocking polling driver for typed public model-job observations."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from parampilot.errors import (
    JobProgressCallbackError,
    JobWaitTimeoutError,
    ParamPilotError,
)
from parampilot.job_waiting.callbacks import ProgressCallback
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


class SyncJobWaiter:
    """Poll one existing remote job without submitting or implicitly canceling it.

    Args:
        monotonic: Monotonic seconds source used for local deadlines.
        sleep: Native blocking sleep boundary.

    """

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Store deterministic time dependencies.

        Args:
            monotonic: Monotonic seconds source used for local deadlines.
            sleep: Native blocking sleep boundary.

        """
        self._monotonic = monotonic
        self._sleep = sleep

    def wait(
        self,
        *,
        campaign_id: UUID | str,
        job_id: UUID | str,
        fetch: Callable[[], ApiResponse[PublicModelJobObservation]],
        result: Callable[[], ResultT],
        cancel: Callable[[], object],
        timeout: float | None,
        poll_interval: float,
        on_progress: ProgressCallback | None,
        cancel_remote: bool,
    ) -> ResultT:
        """Block until an existing job finishes or local waiting terminates.

        Args:
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.
            fetch: Retrieve one typed current observation plus safe metadata.
            result: Retrieve the concrete terminal result.
            cancel: Explicit remote-cancel operation.
            timeout: Positive local timeout or ``None``.
            poll_interval: Client minimum poll interval from 0.01 through 30.
            on_progress: Optional validated significant-change callback.
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
        while True:
            try:
                response = fetch()
            except ParamPilotError as poll_error:
                if cancel_remote:
                    cancel()
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
                    on_progress(last)
                except Exception as error:
                    if cancel_remote:
                        cancel()
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
                    return result()
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
                self._raise_timeout(options, last, cancel, cancel_remote)
            delay = poll_delay(response, poll_interval=options.poll_interval)
            if options.timeout is not None:
                delay = min(delay, options.timeout - elapsed)
            try:
                self._sleep(delay)
            except KeyboardInterrupt:
                if cancel_remote:
                    cancel()
                raise
            if (
                options.timeout is not None
                and self._monotonic() - started >= options.timeout
            ):
                self._raise_timeout(options, last, cancel, cancel_remote)

    @staticmethod
    def _raise_timeout(
        options: WaitOptions,
        last: PublicModelJobObservation | None,
        cancel: Callable[[], object],
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
            cancel()
        raise JobWaitTimeoutError(
            "ParamPilot job waiting exceeded the local timeout",
            campaign_id=options.campaign_id,
            job_id=options.job_id,
            last_observation=last,
        )

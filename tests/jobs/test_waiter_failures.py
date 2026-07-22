"""Synchronous job-wait callback, polling, and interruption tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import NoReturn

import pytest

from parampilot import AuthenticationError, CompatibilityError, ConfigurationError
from parampilot.errors import (
    JobAuthenticationError,
    JobCompatibilityError,
    JobProgressCallbackError,
)
from parampilot.job_waiting.sync_waiter import SyncJobWaiter
from parampilot.models import PublicModelJobObservation
from parampilot.responses import ApiResponse
from tests.jobs.waiter_support import _observation, _train_result
from tests.support import CAMPAIGN_ID, JOB_ID


def test_callback_failure_aborts_wait_without_implicit_remote_cancel() -> None:
    """A caller callback failure must be typed and leave the remote job alone."""
    cancel_calls = 0

    def cancel() -> None:
        """Count any unexpected remote cancellation."""
        nonlocal cancel_calls
        cancel_calls += 1

    def callback(_: PublicModelJobObservation) -> NoReturn:
        """Raise a representative caller failure.

        Raises:
            RuntimeError: Always, to exercise callback policy.

        """
        raise RuntimeError("callback failed")

    waiter = SyncJobWaiter(monotonic=lambda: 0.0, sleep=lambda _: None)

    with pytest.raises(JobProgressCallbackError) as caught:
        waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=lambda: _observation("running"),
            result=_train_result,
            cancel=cancel,
            timeout=10,
            poll_interval=1,
            on_progress=callback,
            cancel_remote=False,
        )

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert cancel_calls == 0


@pytest.mark.parametrize(
    ("failure", "expected_type"),
    [
        (
            AuthenticationError(401, code="authentication_failed"),
            JobAuthenticationError,
        ),
        (CompatibilityError("server contract changed"), JobCompatibilityError),
    ],
)
def test_polling_contract_failures_have_distinct_recoverable_types(
    failure: Exception,
    expected_type: type[JobAuthenticationError | JobCompatibilityError],
) -> None:
    """Auth and compatibility loss must retain state in distinct errors.

    Args:
        failure: Typed underlying polling failure.
        expected_type: Distinct public job-wait exception class.

    """
    observations: Iterator[ApiResponse[PublicModelJobObservation] | Exception] = iter(
        [
            _observation("queued"),
            failure,
        ]
    )

    def fetch() -> ApiResponse[PublicModelJobObservation]:
        """Return one observation and then raise authentication loss.

        Returns:
            First typed observation.

        Raises:
            ParamPilotError: On the second poll.

        """
        value = next(observations)
        if isinstance(value, Exception):
            raise value
        return value

    waiter = SyncJobWaiter(monotonic=lambda: 0.0, sleep=lambda _: None)

    with pytest.raises(expected_type) as caught:
        waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=fetch,
            result=_train_result,
            cancel=lambda: None,
            timeout=10,
            poll_interval=1,
            on_progress=None,
            cancel_remote=False,
        )

    assert caught.value.__cause__ is failure
    assert caught.value.last_observation is not None


@pytest.mark.parametrize(
    ("timeout", "poll_interval"),
    [(0, 1), (float("inf"), 1), (10, 0), (10, 31)],
)
def test_invalid_wait_timing_fails_before_polling(
    timeout: float,
    poll_interval: float,
) -> None:
    """Invalid local timing controls must fail before any job request.

    Args:
        timeout: Invalid timeout candidate or otherwise valid value.
        poll_interval: Invalid poll interval candidate or valid value.

    """
    fetch_calls = 0

    def fetch() -> ApiResponse[PublicModelJobObservation]:
        """Count an unexpected observation request.

        Returns:
            Observation that must remain unreachable.

        """
        nonlocal fetch_calls
        fetch_calls += 1
        return _observation("done")

    waiter = SyncJobWaiter(monotonic=lambda: 0.0, sleep=lambda _: None)

    with pytest.raises(ConfigurationError, match="timeout|poll_interval"):
        waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=fetch,
            result=_train_result,
            cancel=lambda: None,
            timeout=timeout,
            poll_interval=poll_interval,
            on_progress=None,
            cancel_remote=False,
        )

    assert fetch_calls == 0


@pytest.mark.parametrize("cancel_remote", [False, True])
def test_sync_keyboard_interrupt_only_cancels_when_explicit(
    cancel_remote: bool,
) -> None:
    """A local sync interrupt must preserve explicit remote-cancel policy.

    Args:
        cancel_remote: Explicit remote-cancel policy under test.

    """
    cancel_calls = 0

    def interrupt(_: float) -> NoReturn:
        """Raise a local keyboard interrupt at the blocking boundary.

        Raises:
            KeyboardInterrupt: Always.

        """
        raise KeyboardInterrupt

    def cancel() -> None:
        """Count explicit remote cancellation."""
        nonlocal cancel_calls
        cancel_calls += 1

    waiter = SyncJobWaiter(monotonic=lambda: 0.0, sleep=interrupt)

    with pytest.raises(KeyboardInterrupt):
        waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=lambda: _observation("running"),
            result=_train_result,
            cancel=cancel,
            timeout=10,
            poll_interval=1,
            on_progress=None,
            cancel_remote=cancel_remote,
        )

    assert cancel_calls == int(cancel_remote)

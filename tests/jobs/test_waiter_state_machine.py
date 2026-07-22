"""Deterministic synchronous job-wait progress and terminal-state tests."""

from __future__ import annotations

import pytest

from parampilot.errors import (
    JobCanceledError,
    JobFailedError,
    JobWaitTimeoutError,
)
from parampilot.job_waiting.sync_waiter import SyncJobWaiter
from parampilot.models import PublicModelJobObservation, TrainResult
from parampilot.responses import ApiResponse
from tests.jobs.waiter_support import FakeClock, _observation, _train_result
from tests.support import CAMPAIGN_ID, JOB_ID, job_observation_payload


def test_sync_waiter_delivers_distinct_progress_and_honors_retry_after() -> None:
    """Sync polling must deduplicate progress and honor bounded server guidance."""
    clock = FakeClock()
    observations = iter(
        [
            _observation("queued", retry_after="2"),
            _observation("running"),
            _observation("running"),
            _observation("done"),
        ]
    )
    delivered: list[str] = []
    result_calls = 0

    def fetch() -> ApiResponse[PublicModelJobObservation]:
        """Return the next deterministic lifecycle observation.

        Returns:
            Next typed observation response.

        """
        return next(observations)

    def result() -> TrainResult:
        """Return the terminal result while counting retrieval.

        Returns:
            Typed Train result.

        """
        nonlocal result_calls
        result_calls += 1
        return _train_result()

    waiter = SyncJobWaiter(monotonic=clock.monotonic, sleep=clock.sleep)

    terminal = waiter.wait(
        campaign_id=CAMPAIGN_ID,
        job_id=JOB_ID,
        fetch=fetch,
        result=result,
        cancel=lambda: None,
        timeout=20,
        poll_interval=1,
        on_progress=lambda value: delivered.append(value.status.value),
        cancel_remote=False,
    )

    assert terminal.kind == "train"
    assert delivered == ["queued", "running", "done"]
    assert clock.delays == [2.0, 1.0, 1.0]
    assert result_calls == 1


def test_progress_deduplicates_check_time_but_delivers_new_heartbeat() -> None:
    """Liveness check timestamps are noise while new contact is significant."""
    first_payload = job_observation_payload(status="running")
    repeated_payload = job_observation_payload(status="running")
    heartbeat_payload = job_observation_payload(status="running")
    done_payload = job_observation_payload(status="done")
    repeated_payload["liveness"]["checked_at"] = "2026-07-14T12:00:03Z"
    heartbeat_payload["liveness"]["checked_at"] = "2026-07-14T12:00:04Z"
    heartbeat_payload["liveness"]["last_contact_at"] = "2026-07-14T12:00:03Z"
    observations = iter(
        PublicModelJobObservation.model_validate(payload)
        for payload in [
            first_payload,
            repeated_payload,
            heartbeat_payload,
            done_payload,
        ]
    )
    delivered: list[PublicModelJobObservation] = []
    clock = FakeClock()
    waiter = SyncJobWaiter(monotonic=clock.monotonic, sleep=clock.sleep)

    waiter.wait(
        campaign_id=CAMPAIGN_ID,
        job_id=JOB_ID,
        fetch=lambda: ApiResponse(
            data=next(observations),
            status_code=200,
            headers={},
            request_id=None,
            etag=None,
        ),
        result=_train_result,
        cancel=lambda: None,
        timeout=10,
        poll_interval=1,
        on_progress=delivered.append,
        cancel_remote=False,
    )

    assert [value.status.value for value in delivered] == [
        "running",
        "running",
        "done",
    ]
    assert (
        delivered[1].liveness.last_contact_at != delivered[0].liveness.last_contact_at
    )


@pytest.mark.parametrize(
    ("status", "expected_type"),
    [("failed", JobFailedError), ("canceled", JobCanceledError)],
)
def test_sync_waiter_terminal_errors_retain_last_observation(
    status: str,
    expected_type: type[JobFailedError | JobCanceledError],
) -> None:
    """Failed and canceled jobs must raise distinct reconstructable errors.

    Args:
        status: Terminal server lifecycle state.
        expected_type: Public terminal waiter exception.

    """
    observation = _observation(status)
    waiter = SyncJobWaiter(monotonic=lambda: 0.0, sleep=lambda _: None)

    with pytest.raises(expected_type) as caught:
        waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=lambda: observation,
            result=_train_result,
            cancel=lambda: None,
            timeout=10,
            poll_interval=1,
            on_progress=None,
            cancel_remote=False,
        )

    assert str(caught.value.job_id) == JOB_ID
    assert str(caught.value.campaign_id) == CAMPAIGN_ID
    assert caught.value.last_observation is observation.data


@pytest.mark.parametrize("cancel_remote", [False, True])
def test_sync_timeout_preserves_state_and_only_explicitly_cancels(
    cancel_remote: bool,
) -> None:
    """Timeout must use monotonic time and never imply remote cancellation.

    Args:
        cancel_remote: Explicit remote-cancel policy under test.

    """
    clock = FakeClock()
    cancel_calls = 0

    def cancel() -> None:
        """Count an explicit remote cancellation."""
        nonlocal cancel_calls
        cancel_calls += 1

    observation = _observation("running")
    waiter = SyncJobWaiter(monotonic=clock.monotonic, sleep=clock.sleep)

    with pytest.raises(JobWaitTimeoutError) as caught:
        waiter.wait(
            campaign_id=CAMPAIGN_ID,
            job_id=JOB_ID,
            fetch=lambda: observation,
            result=_train_result,
            cancel=cancel,
            timeout=2,
            poll_interval=1,
            on_progress=None,
            cancel_remote=cancel_remote,
        )

    assert caught.value.last_observation is observation.data
    assert cancel_calls == int(cancel_remote)
    assert clock.now == 2

"""Stateful fake public API used by sync and async workflow tests."""

from __future__ import annotations

import json

import httpx

from tests.support import (
    availability_payload,
    canonical_error,
    job_observation_payload,
    job_result_payload,
)
from tests.workflows.fixtures import (
    ASK_JOB_ID,
    INPUT_EXPERIMENT_ID,
    SUGGESTION_ID,
    TRAIN_JOB_ID,
    WORKFLOW_CAPABILITIES,
    RecordedCall,
    experiment_payload,
    model_job_payload,
)


class WorkflowScenario:
    """Stateful deterministic API with injectable workflow-stage failures.

    Args:
        fail_at: Operation label that always returns a typed server failure.
        lose_response_once_at: Operation whose first accepted response is lost.
        training_required_at_ask: Return the freshness precondition at Ask.

    """

    def __init__(
        self,
        *,
        fail_at: str | None = None,
        lose_response_once_at: str | None = None,
        training_required_at_ask: bool = False,
    ) -> None:
        """Initialize failure policy and empty operation trace.

        Args:
            fail_at: Operation label that always returns a typed server failure.
            lose_response_once_at: Operation whose first accepted response is lost.
            training_required_at_ask: Return the freshness precondition at Ask.

        """
        self.fail_at = fail_at
        self.lose_response_once_at = lose_response_once_at
        self.training_required_at_ask = training_required_at_ask
        self.calls: list[RecordedCall] = []
        self._operation_counts: dict[str, int] = {}

    def count(self, operation: str) -> int:
        """Return how often an operation reached the fake server.

        Args:
            operation: Stable test operation label.

        Returns:
            Recorded request count.

        """
        return sum(call.operation == operation for call in self.calls)

    def keys(self, operation: str) -> list[str | None]:
        """Return idempotency keys observed for one operation.

        Args:
            operation: Stable test operation label.

        Returns:
            Keys in request order.

        """
        return [
            call.idempotency_key for call in self.calls if call.operation == operation
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Serve one synchronous HTTPX request.

        Args:
            request: Outbound SDK request.

        Returns:
            Deterministic public response.

        """
        request.read()
        return self._respond(request)

    async def handle_async(self, request: httpx.Request) -> httpx.Response:
        """Serve one asynchronous HTTPX request.

        Args:
            request: Outbound SDK request.

        Returns:
            Deterministic public response.

        """
        await request.aread()
        return self._respond(request)

    def _respond(self, request: httpx.Request) -> httpx.Response:
        """Record and route one fully read public request.

        Args:
            request: Fully buffered fake-transport request.

        Returns:
            Deterministic success or injected typed failure.

        Raises:
            httpx.ReadError: For a configured accepted-but-lost response.

        """
        operation = self._operation(request)
        body = json.loads(request.content) if request.content else None
        self.calls.append(
            RecordedCall(
                operation=operation,
                method=request.method,
                path=request.url.path,
                idempotency_key=request.headers.get("Idempotency-Key"),
                body=body,
            )
        )
        count = self._operation_counts.get(operation, 0) + 1
        self._operation_counts[operation] = count
        if operation == self.lose_response_once_at and count == 1:
            raise httpx.ReadError("accepted response was lost", request=request)
        if operation == self.fail_at:
            return httpx.Response(
                503,
                json=canonical_error("server_error"),
                request=request,
            )
        if operation == "ask_submit" and self.training_required_at_ask:
            return httpx.Response(
                409,
                json=canonical_error(
                    "training_required",
                    context={
                        "model_state": "stale",
                        "required_model_revision": "required-v2",
                        "trained_model_revision": "model-v1",
                    },
                ),
                request=request,
            )
        return self._success(operation, request)

    @staticmethod
    def _operation(request: httpx.Request) -> str:
        """Classify one public request into a stable workflow operation.

        Args:
            request: Outbound SDK request.

        Returns:
            Stable test operation label.

        Raises:
            AssertionError: If the workflow emits an unexpected request.

        """
        path = request.url.path
        if path.endswith("/availability/"):
            return "availability"
        if path.endswith("/experiments/batch-upsert/"):
            return "batch"
        if path.endswith("/model/training-jobs/"):
            return "train_submit"
        if path.endswith("/model/ask-jobs/"):
            return "ask_submit"
        if path.endswith(f"/model/jobs/{TRAIN_JOB_ID}/observation/"):
            return "train_observe"
        if path.endswith(f"/model/jobs/{TRAIN_JOB_ID}/result/"):
            return "train_result"
        if path.endswith(f"/model/jobs/{ASK_JOB_ID}/observation/"):
            return "ask_observe"
        if path.endswith(f"/model/jobs/{ASK_JOB_ID}/result/"):
            return "ask_result"
        if path.endswith("/experiments/"):
            return "suggestions"
        raise AssertionError(f"Unexpected workflow request: {request.method} {path}")

    @staticmethod
    def _success(operation: str, request: httpx.Request) -> httpx.Response:
        """Build the deterministic success response for an operation.

        Args:
            operation: Stable test operation label.
            request: Outbound SDK request.

        Returns:
            Typed public success response.

        """
        if operation == "availability":
            payload = availability_payload(capabilities=WORKFLOW_CAPABILITIES)
        elif operation == "batch":
            payload = {
                "items": [
                    {
                        "index": 0,
                        "created": True,
                        "experiment": experiment_payload(
                            experiment_id=INPUT_EXPERIMENT_ID,
                            labcode="run-001",
                            status="done",
                            inputs={"temperature": 80.0},
                        ),
                    }
                ]
            }
        elif operation == "train_submit":
            payload = model_job_payload(kind="train", job_id=TRAIN_JOB_ID)
        elif operation == "ask_submit":
            payload = model_job_payload(kind="ask", job_id=ASK_JOB_ID)
        elif operation in {"train_observe", "ask_observe"}:
            kind = "train" if operation.startswith("train") else "ask"
            job_id = TRAIN_JOB_ID if kind == "train" else ASK_JOB_ID
            payload = job_observation_payload(status="done", kind=kind)
            payload["id"] = job_id
        elif operation == "train_result":
            payload = job_result_payload(kind="train")
        elif operation == "ask_result":
            payload = {"kind": "ask", "created_experiment_ids": [SUGGESTION_ID]}
        elif operation == "suggestions":
            payload = {
                "items": [
                    experiment_payload(
                        experiment_id=SUGGESTION_ID,
                        labcode="candidate-001",
                        status="pending",
                        inputs={"temperature": 91.0},
                    )
                ],
                "next_cursor": None,
                "has_more": False,
                "snapshot_at": "2026-07-14T12:00:00Z",
            }
        else:
            raise AssertionError(f"No success fixture for {operation}")
        status = 202 if operation in {"train_submit", "ask_submit"} else 200
        return httpx.Response(status, json=payload, request=request)

"""Coverage tests binding every OpenAPI operation to the async client surface."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from parampilot import AsyncParamPilot
from parampilot.errors import AuthenticationError
from parampilot.models import Domain, RandomStrategy
from tests.resources.operation_calls import invoke_operation
from tests.support import (
    CAMPAIGN_ID,
    EXPERIMENT_ID,
    JOB_ID,
    TOKEN,
    availability_payload,
    canonical_error,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
COVERAGE_PATH = PACKAGE_ROOT / "contracts" / "operation-coverage.json"
OPERATIONS_PATH = PACKAGE_ROOT / "src" / "parampilot" / "generated" / "operations.json"
CAPABILITIES = [
    "artifacts.grid-predictions",
    "artifacts.shap-results",
    "campaigns.configured-create",
    "campaigns.effects",
    "experiments.batch-upsert",
    "experiments.effective",
    "jobs.explicit-training",
    "jobs.observations",
]


def _coverage() -> dict[str, Any]:
    """Load the reviewed operation coverage manifest.

    Returns:
        Decoded coverage document.

    """
    value = json.loads(COVERAGE_PATH.read_text())
    assert isinstance(value, dict)
    return value


def _domain_and_strategy() -> tuple[Domain, RandomStrategy]:
    """Build minimal valid contracts reused by operation invocations.

    Returns:
        Typed domain and matching random strategy.

    """
    domain = Domain.model_validate(
        {
            "type": "Domain",
            "inputs": {
                "type": "Inputs",
                "features": [
                    {
                        "type": "ContinuousInput",
                        "key": "temperature",
                        "bounds": [20.0, 100.0],
                    }
                ],
            },
            "outputs": {
                "type": "Outputs",
                "features": [
                    {
                        "type": "ContinuousOutput",
                        "key": "yield",
                        "objective": {"type": "MaximizeObjective"},
                    }
                ],
            },
            "constraints": {"type": "Constraints", "constraints": []},
        }
    )
    strategy = RandomStrategy.model_validate(
        {"type": "RandomStrategy", "domain": domain, "seed": 42}
    )
    return domain, strategy


@pytest.mark.asyncio
async def test_every_openapi_operation_is_an_implemented_async_method() -> None:
    """All reviewed operations must resolve to concrete coroutine methods."""
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    coverage = _coverage()
    for operation_id, entry in coverage["operations"].items():
        assert entry["status"] == "implemented", operation_id
        owner = (
            client
            if entry["resource"] == "client"
            else getattr(client, entry["resource"])
        )
        method = getattr(owner, entry["method"])
        assert inspect.iscoroutinefunction(method), operation_id

    await client.close()
    await http_client.aclose()


def test_only_train_named_async_method_can_submit_training() -> None:
    """The async operation map must preserve the sole explicit training trigger."""
    coverage = _coverage()["operations"]
    train_capable = {
        operation_id: entry
        for operation_id, entry in coverage.items()
        if entry["may_train"]
    }

    assert set(train_capable) == {"createTrainingJob"}
    assert train_capable["createTrainingJob"]["method"] == "train_model"
    assert not any(
        entry["may_train"]
        for operation_id, entry in coverage.items()
        if "Ask" in operation_id or "Prediction" in operation_id
    )


@pytest.mark.asyncio
async def test_every_async_method_reaches_its_exact_generated_operation() -> None:
    """All resource methods must build their reviewed method/path before decoding."""
    operations_document = json.loads(OPERATIONS_PATH.read_text())
    operations = {
        item["operation_id"]: item for item in operations_document["operations"]
    }
    domain, strategy = _domain_and_strategy()
    path_values = {
        "campaign_id": CAMPAIGN_ID,
        "experiment_id": EXPERIMENT_ID,
        "grant_id": EXPERIMENT_ID,
        "job_id": JOB_ID,
        "link_id": EXPERIMENT_ID,
    }

    for operation_id, metadata in operations.items():
        captured: list[httpx.Request] = []

        async def handler(
            request: httpx.Request,
            target_operation_id: str = operation_id,
            captured_requests: list[httpx.Request] = captured,
        ) -> httpx.Response:
            """Serve capability checks and reject the target operation.

            Args:
                request: Outbound SDK request.
                target_operation_id: Loop-bound target operation ID.
                captured_requests: Loop-bound target request collection.

            Returns:
                Availability or canonical authentication failure.

            """
            if (
                request.url.path.endswith("/availability/")
                and target_operation_id != "getAvailability"
            ):
                return httpx.Response(
                    200,
                    json=availability_payload(capabilities=CAPABILITIES),
                    request=request,
                )
            captured_requests.append(request)
            return httpx.Response(
                401,
                json=canonical_error("authentication_failed"),
                request=request,
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncParamPilot(
            base_url="https://example.test",
            token=TOKEN,
            http_client=http_client,
        )

        with pytest.raises(AuthenticationError) as caught:
            await invoke_operation(client, operation_id, domain, strategy)

        expected_path = metadata["path"]
        for name, value in path_values.items():
            expected_path = expected_path.replace(f"{{{name}}}", value)
        assert caught.value.operation_id == operation_id
        assert len(captured) == 1
        assert captured[0].method == metadata["method"]
        assert captured[0].url.path == expected_path
        await client.close()
        await http_client.aclose()

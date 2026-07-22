"""Coverage and signature parity tests for the synchronous public surface."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from parampilot import AsyncParamPilot, ParamPilot
from parampilot.errors import AuthenticationError
from tests.resources.sync_operation_calls import invoke_sync_operation
from tests.support import (
    CAMPAIGN_ID,
    EXPERIMENT_ID,
    JOB_ID,
    TOKEN,
    availability_payload,
    canonical_error,
    domain_and_strategy,
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
RESOURCE_NAMES = (
    "campaigns",
    "campaign_access",
    "campaign_transfer_links",
    "experiments",
    "model_jobs",
    "model_artifacts",
    "workflows",
)


def _coverage() -> dict[str, Any]:
    """Load the reviewed operation manifest.

    Returns:
        Decoded operation coverage document.

    """
    value = json.loads(COVERAGE_PATH.read_text())
    assert isinstance(value, dict)
    return value


def _normalized_signature(callable_object: object) -> str:
    """Normalize natural sync/async annotation differences for comparison.

    Args:
        callable_object: Bound public method to inspect.

    Returns:
        Stable signature text with only allowed modality names normalized.

    """
    value = str(inspect.signature(callable_object))
    return (
        value.replace("AsyncIterator", "Iterator")
        .replace("AsyncDownload", "Download")
        .replace("AsyncProgressCallback", "ProgressCallback")
        .replace("AsyncWorkflowProgressCallback", "WorkflowProgressCallback")
        .replace("AsyncParamPilot", "ParamPilot")
        .replace("httpx.AsyncClient", "httpx.Client")
    )


def test_every_openapi_operation_is_an_implemented_sync_method() -> None:
    """All reviewed operations must resolve to concrete native sync methods."""
    http_client = httpx.Client(transport=httpx.MockTransport(lambda _: None))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    for operation_id, entry in _coverage()["operations"].items():
        owner = (
            client
            if entry["resource"] == "client"
            else getattr(client, entry["resource"])
        )
        method = getattr(owner, entry["method"])
        assert callable(method), operation_id
        assert not inspect.iscoroutinefunction(method), operation_id

    client.close()
    http_client.close()


@pytest.mark.asyncio
async def test_async_and_sync_public_method_signatures_remain_equivalent() -> None:
    """Changing either client surface must fail until its peer is updated."""
    async_http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None))
    sync_http = httpx.Client(transport=httpx.MockTransport(lambda _: None))
    async_client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=async_http,
    )
    sync_client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=sync_http,
    )

    assert _normalized_signature(AsyncParamPilot) == _normalized_signature(ParamPilot)
    assert _normalized_signature(async_client.get_availability) == (
        _normalized_signature(sync_client.get_availability)
    )
    assert _normalized_signature(async_client.check_compatibility) == (
        _normalized_signature(sync_client.check_compatibility)
    )
    assert _normalized_signature(async_client.request) == _normalized_signature(
        sync_client.request
    )
    for resource_name in RESOURCE_NAMES:
        async_resource = getattr(async_client, resource_name)
        sync_resource = getattr(sync_client, resource_name)
        async_methods = {
            name
            for name, value in inspect.getmembers(async_resource, callable)
            if not name.startswith("_")
        }
        sync_methods = {
            name
            for name, value in inspect.getmembers(sync_resource, callable)
            if not name.startswith("_")
        }
        assert sync_methods == async_methods, resource_name
        for method_name in async_methods:
            assert _normalized_signature(getattr(async_resource, method_name)) == (
                _normalized_signature(getattr(sync_resource, method_name))
            ), f"{resource_name}.{method_name}"

    sync_client.close()
    sync_http.close()  # noqa: ASYNC212 - native sync parity under an active loop
    await async_client.close()
    await async_http.aclose()


def test_every_sync_method_reaches_its_exact_generated_operation() -> None:
    """All sync methods must build the reviewed method/path before decoding."""
    operations_document = json.loads(OPERATIONS_PATH.read_text())
    domain, strategy = domain_and_strategy()
    path_values = {
        "campaign_id": CAMPAIGN_ID,
        "experiment_id": EXPERIMENT_ID,
        "grant_id": EXPERIMENT_ID,
        "job_id": JOB_ID,
        "link_id": EXPERIMENT_ID,
    }

    for metadata in operations_document["operations"]:
        operation_id = metadata["operation_id"]
        captured: list[httpx.Request] = []

        def handler(
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

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        client = ParamPilot(
            base_url="https://example.test",
            token=TOKEN,
            http_client=http_client,
        )

        with pytest.raises(AuthenticationError) as caught:
            invoke_sync_operation(client, operation_id, domain, strategy)

        expected_path = metadata["path"]
        for name, value in path_values.items():
            expected_path = expected_path.replace(f"{{{name}}}", value)
        assert caught.value.operation_id == operation_id
        assert len(captured) == 1
        assert captured[0].method == metadata["method"]
        assert captured[0].url.path == expected_path
        client.close()
        http_client.close()

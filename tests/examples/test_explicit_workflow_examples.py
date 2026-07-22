"""Run published sync and async workflow examples against safe fake HTTP."""

from __future__ import annotations

import httpx
import pytest

from examples.async_explicit_training_workflow import run_async_workflow
from examples.sync_explicit_training_workflow import run_sync_workflow
from parampilot import AsyncParamPilot, ParamPilot
from parampilot.workflow_models import WorkflowStage
from tests.support import CAMPAIGN_ID, TOKEN
from tests.workflows.fixtures import EXPERIMENTS
from tests.workflows.support import WorkflowScenario


def test_sync_documentation_example_executes_without_real_training() -> None:
    """The sync-first example must run solely through its supplied client."""
    scenario = WorkflowScenario()
    http_client = httpx.Client(transport=httpx.MockTransport(scenario.handle))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = run_sync_workflow(client, CAMPAIGN_ID, EXPERIMENTS, n=1)

    assert result.checkpoint.stage is WorkflowStage.completed
    assert scenario.count("train_submit") == 1
    client.close()
    http_client.close()


@pytest.mark.asyncio
async def test_async_documentation_example_executes_without_real_training() -> None:
    """The async example must reuse one supplied long-lived async client."""
    scenario = WorkflowScenario()
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(scenario.handle_async)
    )
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    result = await run_async_workflow(client, CAMPAIGN_ID, EXPERIMENTS, n=1)

    assert result.checkpoint.stage is WorkflowStage.completed
    assert scenario.count("train_submit") == 1
    await client.close()
    await http_client.aclose()

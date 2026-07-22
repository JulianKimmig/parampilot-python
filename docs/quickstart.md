# ParamPilot Python SDK quickstart

## Install and authenticate

Install the public package with your normal Python package manager:

```bash
python -m pip install parampilot
```

Create a programmatic API token in the ParamPilot account interface. The raw
token is shown only at creation time. Store it in your secret manager or set
`PARAMPILOT_API_TOKEN`; never put it in source code, notebooks, checkpoints, or
logs. Pass the deployment's HTTPS base URL separately.

```bash
export PARAMPILOT_API_TOKEN='<token shown by ParamPilot>'
```

## Five-minute synchronous flow

`ParamPilot` is a native blocking client. It does not require asyncio and is
the shortest path for scripts, notebooks, and most lab automation.

The following assumes a configured, started campaign. `experiments` may also
be an `ExperimentBatchUpsertRequest` if you prefer to construct every generated
Pydantic model explicitly.

```python
from parampilot import ParamPilot

campaign_id = "00000000-0000-0000-0000-000000000000"
experiments = [
    {
        "labcode": "run-001",
        "inputs": {"temperature": 80.0},
        "outputs": {"yield": 73.0},
        "valid_outputs": {"yield": True},
    }
]

with ParamPilot(base_url="https://your-parampilot.example") as client:
    result = client.workflows.add_experiments_train_and_ask(
        campaign_id,
        experiments,
        n=5,
        idempotency_key="esterification-round-0001",
    )
    for suggestion in result.suggested_experiments:
        print(suggestion.id, suggestion.inputs)
```

The method name deliberately contains `train`: it atomically upserts the batch,
submits one explicit Train job, waits for it, submits a non-training Ask job,
waits for it, and returns the complete Ask-created experiment resources. It is
not one database transaction. The returned checkpoint records every committed
stage and both job IDs.

Runnable, type-checked versions live in
[`examples/sync_explicit_training_workflow.py`](../examples/sync_explicit_training_workflow.py)
and
[`examples/async_explicit_training_workflow.py`](../examples/async_explicit_training_workflow.py).

## Upload experiments without training

Use the lower-level batch resource when data ingestion is the only intended
operation. Batch upsert is atomic for one through 500 rows, preserves row order
in its typed result, and never starts model training.

```python
from parampilot.models import ExperimentBatchUpsertRequest

batch_request = ExperimentBatchUpsertRequest.model_validate(
    {"items": experiments}
)
with ParamPilot(base_url="https://your-parampilot.example") as client:
    batch_result = client.experiments.batch_upsert(
        campaign_id,
        batch_request,
        idempotency_key="esterification-data-0001",
    )
```

The async client exposes the same call as
`await client.experiments.batch_upsert(...)`. Submit Train separately only when
that is the deliberate next action.

## Create and start a configured campaign

Campaign configuration uses the generated public Pydantic models. A strategy
contains the same domain it operates on.

```python
from parampilot.models import (
    ConfiguredCampaignCreateRequest,
    Domain,
    ExtraData,
    RandomStrategy,
)

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
strategy = RandomStrategy(domain=domain, seed=42)

with ParamPilot(base_url="https://your-parampilot.example") as client:
    campaign = client.campaigns.create_configured(
        ConfiguredCampaignCreateRequest(
            name="Esterification",
            domain=domain,
            strategy=strategy,
            additional_fields=ExtraData(fields=[]),
            effects=[],
        ),
        idempotency_key="create-esterification-0001",
    )
    current = client.campaigns.get_with_metadata(campaign.id)
    started = client.campaigns.start(
        campaign.id,
        if_match=current.require_etag(),
        idempotency_key="start-esterification-0001",
    )
```

Creating, configuring, starting, importing, or changing experiments never
trains a model. Use `model_jobs.train_model()` or a public workflow whose name
contains `train` when you intentionally want training.

## Next steps

- [Workflows, jobs, and recovery](workflows-and-recovery.md)
- [Package README and API overview](../README.md)

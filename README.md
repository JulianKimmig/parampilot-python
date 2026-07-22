# ParamPilot Python SDK

`parampilot` is the typed public Python client for the ParamPilot programmatic
API. It provides native asynchronous and synchronous clients backed by HTTPX
and validates JSON contracts with Pydantic.

The SDK is standalone: installing it does not install or import the private
ParamPilot backend, worker, Django, or the optimization runtime.

Start with the [sync-first quickstart](docs/quickstart.md), then see
[workflows, jobs, and recovery](docs/workflows-and-recovery.md).

## Installation

```bash
python -m pip install parampilot
```

## Authentication

Create a programmatic API token in the ParamPilot account interface. The raw
token is shown only when it is created. Pass it explicitly or store it in the
`PARAMPILOT_API_TOKEN` environment variable; the SDK never creates, persists,
or displays tokens.

## Synchronous quick start

```python
from parampilot import ParamPilot, TrainingRequiredError
from parampilot.models import CampaignCreateRequest

with ParamPilot(base_url="https://your-parampilot.example") as client:
    campaign = client.campaigns.create(
        CampaignCreateRequest(name="Esterification")
    )
    for summary in client.campaigns.iterate(limit=100):
        print(summary.name)

    try:
        client.model_jobs.create_ask_job(campaign.id, n=5)
    except TrainingRequiredError as error:
        print(error.context["model_state"])
```

`ParamPilot` is a native blocking client backed by `httpx.Client`; it does not
create or manage an asyncio event loop. It exposes the same resource names,
method parameters, generated models, errors, retries, pagination, downloads,
and compatibility behavior as `AsyncParamPilot`. Blocking the calling thread
is expected; use `AsyncParamPilot` for high-concurrency applications. Both
clients accept the same `timeout`, `max_retries`, and `retry_backoff` options.

## Asynchronous quick start

```python
import asyncio

from parampilot import AsyncParamPilot


async def main() -> None:
    """Print the connected ParamPilot API version."""

    async with AsyncParamPilot(
        base_url="https://your-parampilot.example"
    ) as client:
        availability = await client.get_availability()
        print(availability.api_version)


asyncio.run(main())
```

Both clients expose typed resources for campaigns and configuration, campaign
access and transfer links, experiments and effective-data exports, model jobs
and observations, and model artifacts. Request bodies are generated Pydantic
models; JSON responses are generated Pydantic results. The async equivalent of
the synchronous resource example is:

```python
from parampilot import AsyncParamPilot, TrainingRequiredError
from parampilot.models import CampaignCreateRequest


async def create_and_list() -> None:
    """Create a draft, then lazily list visible campaigns."""

    async with AsyncParamPilot(
        base_url="https://your-parampilot.example"
    ) as client:
        campaign = await client.campaigns.create(
            CampaignCreateRequest(name="Esterification")
        )
        async for summary in client.campaigns.iterate(limit=100):
            print(summary.name)

        try:
            await client.model_jobs.create_ask_job(campaign.id, n=5)
        except TrainingRequiredError as error:
            print(error.context["model_state"])
```

Model training is never implicit. Experiment changes, candidate requests, and
predictions do not train a model. Only methods and workflows whose names
explicitly contain `train` or `training` may request training.

The sole training submission is a deliberate, visibly named call in either
client:

```python
training_job = client.model_jobs.train_model(campaign_id)  # ParamPilot
training_job = await async_client.model_jobs.train_model(  # AsyncParamPilot
    campaign_id
)
```

## Waiting for model jobs

Submission remains nonblocking by default. Set `wait=True` only when the
calling thread or coroutine should wait for the typed terminal result:

```python
train_result = client.model_jobs.train_model(
    campaign_id,
    wait=True,
    timeout=600,
)
ask_result = client.model_jobs.create_ask_job(
    campaign_id,
    n=5,
    wait=True,
)
```

The asynchronous methods accept the same controls and are awaited. Ask and
Predict waiting never submit training; if the campaign needs a current model,
they preserve the server's `TrainingRequiredError`.

Use `client.model_jobs.wait(campaign_id, job_id, ...)` for an already submitted
job. Its progress callback receives validated `PublicModelJobObservation`
objects only when lifecycle, structured progress, liveness, or terminal state
meaningfully changes. A local timeout, `KeyboardInterrupt`, or asyncio task
cancellation leaves the remote job running. Remote cancellation occurs only
through `client.model_jobs.cancel(...)` or an explicit `cancel_remote=True`.

`TrainingJobHandle`, `AskJobHandle`, and `PredictJobHandle` are frozen,
serializable references containing only campaign ID, job ID, and job kind. Pass
a currently open client to their `refresh`, `wait`, `result`, or `cancel`
methods; the handles never retain or serialize a token or HTTP client.

Failed, canceled, timed-out, authentication-lost, compatibility-lost, generic
polling, and progress-callback failures use distinct `JobWaitError` subclasses.
They retain the public job identifiers and last validated observation for safe
recovery. Callback failures abort only the local wait unless remote cancellation
was explicitly requested.

## Explicit composite workflow

The ergonomic one-call flow keeps training visible in its name:

```python
result = client.workflows.add_experiments_train_and_ask(
    campaign_id,
    experiments,
    n=5,
    idempotency_key="optimization-round-0001",
)
```

It validates locally, atomically upserts the experiment batch, explicitly
submits and waits for Train, submits and waits for non-training Ask, then
returns complete suggested `ExperimentResponse` values in Ask order. The call
is not an atomic server transaction. Its typed checkpoint records partial
completion, deterministic operation subkeys, and Train/Ask job IDs.

`AddExperimentsTrainAndAskError` carries that checkpoint. Resume without
duplicating accepted rows, job submissions, or completed training:

```python
result = client.workflows.resume_add_experiments_train_and_ask(
    error.checkpoint,
    experiments,
    n=5,
)
```

Progress events distinguish upload, training, Ask, suggestion retrieval, and
terminal completion. Callback failure never retries or remotely cancels work.
The async methods expose the same contract and are awaited.

Collection `list(...)` methods fetch one typed bounded page. Matching
`iterate(...)` methods follow opaque cursors lazily without prefetching. Binary
exports and grid artifacts return `Download` or `AsyncDownload`; iterate their
chunks, call `read()` only when explicit buffering is intended, or stream to a
caller-chosen path:

```python
download = client.experiments.export(campaign_id, format="csv")
download.write_to("experiments.csv")

download = await client.experiments.export(campaign_id, format="csv")
await download.write_to("experiments.csv")
```

Existing-resource mutations require the ETag returned by a metadata-aware read:

```python
response = await client.campaigns.get_with_metadata(campaign_id)
updated = await client.campaigns.start(
    campaign_id,
    if_match=response.require_etag(),
)
```

The client generates idempotency keys unless one is supplied, retries only
generated operations classified as safe reads or keyed mutations, never
follows redirects, and maps canonical errors to public exception types. The
default compatibility mode warns on a same-major schema-digest difference;
pass `schema_compatibility="strict"` to require the exact generated contract or
call `check_compatibility(...)` with required capability names explicitly.

`ParamPilot.request(...)` and `AsyncParamPilot.request(...)` are intentionally
untyped escape hatches. They are restricted to rooted `/papi/v2/` paths and
retain the SDK's authentication, redirect, timeout, error, and redaction
behavior.

## Development

The package uses `uv` and stores pytest configuration in `pytest.toml`:

```bash
uv sync --all-groups --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv audit --locked
uv build --no-build-isolation
```

Generated contracts are derived solely from the committed public OpenAPI
artifact. Generated files must not be edited by hand.

See [contributing](CONTRIBUTING.md) for the complete local quality gates,
[release and compatibility](docs/release-and-compatibility.md) for the audited
history-isolated extraction and rollback workflow, [security](SECURITY.md) for
private vulnerability reporting, and the [changelog](CHANGELOG.md) for release
contents.

To synchronize the private backend handoff and regenerate every public model,
operation, export, and provenance artifact:

```bash
uv run python -m parampilot_codegen \
  --schema-source <parampilot-backend>/schemas/programmatic-openapi.json
uv run python -m parampilot_codegen --check
```

## License

Apache-2.0. See `LICENSE` and `NOTICE`.

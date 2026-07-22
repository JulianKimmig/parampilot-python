# Workflows, jobs, and recovery

## Composite workflow contract

`client.workflows.add_experiments_train_and_ask(...)` and its awaited async
equivalent execute these visible stages:

| Checkpoint stage | Durable work completed |
| --- | --- |
| `initialized` | Local validation, request fingerprint, and subkeys only |
| `experiments_upserted` | Atomic batch upsert completed |
| `training_submitted` | Explicit Train job accepted; job ID retained |
| `training_completed` | Existing Train job completed; typed result retained |
| `ask_submitted` | Non-training Ask job accepted; job ID retained |
| `ask_completed` | Existing Ask job completed; created IDs retained |
| `completed` | Complete suggested experiments retrieved in Ask order |

Later failure never rolls back earlier server work. The SDK raises
`AddExperimentsTrainAndAskError` with `checkpoint` and `failed_phase`. The
checkpoint contains public UUIDs, typed completed results, a SHA-256 request
fingerprint, and derived idempotency subkeys; it contains no token, client, or
base URL.

## Resume after partial completion

Serialize the checkpoint anywhere appropriate for your data. Supply the
original experiment request and `n` when resuming; a mismatch fails locally
before any HTTP request.

```python
from parampilot import (
    AddExperimentsTrainAndAskCheckpoint,
    AddExperimentsTrainAndAskError,
)

try:
    result = client.workflows.add_experiments_train_and_ask(
        campaign_id,
        experiments,
        n=5,
        idempotency_key="esterification-round-0001",
    )
except AddExperimentsTrainAndAskError as error:
    serialized = error.checkpoint.model_dump_json()
    checkpoint = AddExperimentsTrainAndAskCheckpoint.model_validate_json(serialized)
    result = client.workflows.resume_add_experiments_train_and_ask(
        checkpoint,
        experiments,
        n=5,
    )
```

Each operation uses a deterministic, bounded subkey derived from the caller's
workflow key. A response lost after server acceptance is replayed under that
same subkey. A resumed `training_submitted` checkpoint waits for the existing
Train job; a `training_completed` checkpoint never submits Train again.

If no workflow key is supplied, the SDK generates one and the returned/error
checkpoint is sufficient for normal resume. Supply your own stable key when
you also need recovery from abrupt process loss before Python can persist a
checkpoint. Reusing a stable key with different request data is rejected by
the backend's idempotency fingerprint.

If the campaign changes after Train but before Ask, the backend returns
`TrainingRequiredError`. The workflow preserves the training-completed
checkpoint and does not silently retrain; start a deliberate new train-named
workflow after deciding how to handle the campaign change.

## Progress callbacks

Callbacks receive a validated `WorkflowProgressEvent` with `phase`, `status`,
the current checkpoint, and an optional validated job observation. Phases are
`upload`, `training`, `ask`, `suggestions`, and `terminal`, so training cannot
be hidden in generic progress text. Async callbacks may be awaitable.

A callback failure raises `WorkflowProgressCallbackError`. It does not retry a
completed stage or cancel a remote job. Resume with the attached checkpoint.

## Direct job waiting and cancellation

Use the lower-level API when you do not want the composite workflow:

```python
job = client.model_jobs.train_model(campaign_id)
handle = client.model_jobs.handle(job)
result = handle.wait(client, timeout=600, poll_interval=1)
```

Submission is nonwaiting by default. `wait=True` returns the concrete terminal
result. A local timeout, keyboard interruption, or asyncio cancellation leaves
the remote job running unless direct waiting explicitly receives
`cancel_remote=True`. You may always call `model_jobs.cancel(...)` yourself;
use a stable cancellation idempotency key.

Ask and Predict never train. They raise `TrainingRequiredError` when the model
is missing or stale.

## Async usage

Reuse one long-lived `AsyncParamPilot`; do not construct a new client per call.

```python
async with AsyncParamPilot(base_url="https://your-parampilot.example") as client:
    result = await client.workflows.add_experiments_train_and_ask(
        campaign_id,
        experiments,
        n=5,
        idempotency_key="esterification-round-0001",
    )
```

The synchronous and asynchronous workflow signatures and terminal semantics
are equivalent. The synchronous client uses native `httpx.Client`; it does not
run a hidden event loop or thread.

## Pagination, artifacts, and compatibility

- Collection `list(...)` methods fetch one page. `iterate(...)` follows opaque
  cursors lazily with the same stable filters.
- Binary experiment exports and grid artifacts return `Download` or
  `AsyncDownload`; stream chunks or write to a caller-selected path.
- Grid and SHAP artifacts can be stale and surface `TrainingRequiredError`;
  reads never train.
- Capability checks happen lazily. The default schema policy warns for a
  same-major digest mismatch. Use `schema_compatibility="strict"` to reject it,
  or call `check_compatibility(...)` explicitly.
- Canonical HTTP failures retain safe request IDs, stable codes, retryability,
  issues, and allowlisted context. Workflow errors add only the token-free
  checkpoint and failed phase.

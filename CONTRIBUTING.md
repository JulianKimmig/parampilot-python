# Contributing to ParamPilot Python

Thank you for improving the public ParamPilot SDK.

## Development setup

Use Python 3.10 through 3.14 and [uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-groups --locked
uv run python -m parampilot_codegen --check
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv audit --locked
uv build --no-build-isolation
```

Write pytest behavior tests before implementation. Keep handwritten source
modules at or below 300 lines, use detailed module/class/function docstrings,
and keep the sync and async public surfaces equivalent.

## API contract changes

The private ParamPilot backend is authoritative for the programmatic OpenAPI
contract. Generated files under `src/parampilot/generated/` and the model stub
must not be edited by hand. A public contribution that needs a server change
should begin with an issue describing the desired public behavior. Once the
backend publishes a reviewed OpenAPI handoff, regenerate with:

```bash
uv run python -m parampilot_codegen \
  --schema-source /path/to/programmatic-openapi.json
uv run python -m parampilot_codegen --check
```

The public repository never needs the private backend source to test or build.

## Training boundary

Ask, Predict, data mutation, retries, and polling must never train a model.
Only public methods or workflows whose names contain `train` or `training` may
submit Train. New convenience APIs must preserve this rule and expose
idempotency and partial recovery rather than hiding multi-call work.

## Security and release changes

Do not include real tokens, private hosts, user data, private package imports,
absolute workspace paths, or direct/local/Git dependencies. See
[SECURITY.md](SECURITY.md) for private vulnerability reporting. Pull requests
never publish, tag, push another branch, or run real model training by default.

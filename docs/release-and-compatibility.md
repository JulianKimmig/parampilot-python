# Release, compatibility, and recovery

## Compatibility contract

The machine-readable source of this table is
[`contracts/release-compatibility.json`](../contracts/release-compatibility.json).
The exact locked runtime dependency closure and reviewed SPDX licenses are in
[`contracts/runtime-dependency-review.json`](../contracts/runtime-dependency-review.json).

| Surface | Unreleased 0.1.0 candidate |
| --- | --- |
| Python | 3.10, 3.11, 3.12, 3.13, 3.14 |
| ParamPilot programmatic API | `>=2.0.0,<3.0.0` |
| HTTPX | `>=0.28.1,<1` |
| Pydantic | `>=2.12,<3` |
| OpenAPI digest | `sha256:a657824fc73aac598a530652348f441b7c3c3f37641d1d6972617487b8b6b1db` |

| SDK/server combination | Result |
| --- | --- |
| SDK `0.1.x`, API `2.x`, exact schema digest | Supported |
| SDK `0.1.x`, API `2.x`, different digest | Warn by default; strict mode rejects |
| SDK `0.1.x`, API `1.x` or `3.x` | Rejected as an API-major mismatch |
| Older public SDK releases | Not applicable; no version has been published |

The client checks API major, capabilities, and schema digest lazily. The
default policy warns about a same-major schema difference; strict mode rejects
it. A different API major is incompatible. Generated request/response models
remain tied to the committed digest even when warn mode permits a compatible
server patch.

## History-isolated extraction

Run extraction only from a clean reviewed private commit and choose a new
destination outside the private repository:

```bash
uv run python -m parampilot_release extract \
  --repository-root /path/to/private-parampilot \
  --source-commit <full-reviewed-commit> \
  --output-root /tmp/parampilot-python-public
```

Add `--deny-literal <private-host-or-organization>` for deployment-specific
text that must not cross the boundary. The command copies only tracked
allowlisted SDK files, carries no `.git` directory/history, and emits
`.parampilot-public-manifest.json` with relative paths, exact hashes, schema
and generator identity, and the source commit. It performs the same audit
before making the destination visible.

The reviewed source paths live in
[`contracts/public-source-allowlist.txt`](../contracts/public-source-allowlist.txt).
The extractor rejects missing entries and newly tracked files that have not
been added to that exact list, including files nested under otherwise public
directories.

The generated `.parampilot-public-manifest.json` is an audit record in the
extracted public tree, not a private-source allowlist entry or sdist member.
Public-repository tests exclude it when reconstructing a private-style source
fixture, while the standalone audit command verifies it before any Git history
is created.

Re-audit without modifying the tree:

```bash
uv run python -m parampilot_release audit \
  --public-root /tmp/parampilot-python-public
```

## Release-candidate dry run

From the extracted tree, with no publication credentials present:

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

The runtime closure is approved for the initial candidate under MIT,
BSD-3-Clause, MPL-2.0, and PSF-2.0 terms. Any lock change that alters that
closure must update the machine-readable review before the release tests pass.

Inspect both archives, record their SHA-256 digests, then install the exact
wheel into a clean environment outside either repository. Verify imports,
39-operation metadata, `py.typed`, licensing, runtime dependencies, and the
absence of `parampilot_codegen`, `parampilot_release`, backend, worker, Django,
and BoFire runtime modules from the wheel.

The default public SDK dry run uses fake HTTP and synthetic backend contracts.
It never runs real model fitting. The private source-of-truth repository ran the
separately selected real-worker profile before extraction; that profile is not
part of the public SDK tree. It was local, credential-free, network-free, and
bounded by a 300-second shell timeout. Four synthetic rows and in-memory
artifacts required no post-run cleanup. Stale Ask and Predict claims required
explicit training, one real Train fit produced the artifact pair, and that
exact pair drove successful Ask and Predict jobs without another fit. The
approved profile passed in 50.53 seconds on 2026-07-15.

With the reviewed archives in `dist/` and no publication credentials
configured, validate the registry payload locally without uploading it:

```bash
uv publish --dry-run --no-attestations dist/*
```

The `0.1.0` candidate uses generated-schema provenance, the exact extraction
manifest, the locked dependency review, and archive hashes as its complete
manifest-only provenance set. The owner selected no signed registry attestation
or separate SBOM for this candidate.

## Publication approval and rollback

CI and pull requests validate only; they contain no upload or push step. The
owner approved version `0.1.0`, manifest-only provenance, the local synthetic
real-worker result, no additional deny literals, the reviewed public/synthetic
data, no external v1 consumers, and a candidate/dry-run-only disposition on
2026-07-15. The exact source commit, manifest digest, sdist/wheel hashes, and
public tree still require approval after the final clean candidate is built.

Registry artifacts are immutable. If post-publication verification fails,
stop promotion and yank the affected PyPI version rather than overwrite it.
Publish a corrected higher version, revoke any exposed token, and document the
affected server/SDK range. Do not rewrite or expose private source history.

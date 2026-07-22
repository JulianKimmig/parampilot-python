"""Sync-first example for uploading data, explicitly training, and asking."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from parampilot import AddExperimentsTrainAndAskResult, ParamPilot


def run_sync_workflow(
    client: ParamPilot,
    campaign_id: UUID | str,
    experiments: Sequence[Mapping[str, object]],
    *,
    n: int = 5,
    idempotency_key: str | None = None,
) -> AddExperimentsTrainAndAskResult:
    """Upload an atomic batch, explicitly Train, and return suggested rows.

    Args:
        client: Open native synchronous ParamPilot client.
        campaign_id: Started and configured campaign UUID.
        experiments: One through 500 complete experiment row mappings.
        n: Number of suggested experiments from 1 through 500.
        idempotency_key: Stable workflow key recommended for crash recovery.

    Returns:
        Completed recovery checkpoint and ordered suggested experiments.

    """
    return client.workflows.add_experiments_train_and_ask(
        campaign_id,
        experiments,
        n=n,
        idempotency_key=idempotency_key,
    )

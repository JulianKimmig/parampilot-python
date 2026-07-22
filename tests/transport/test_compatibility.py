"""Availability compatibility policy tests for both native clients."""

from __future__ import annotations

import httpx
import pytest

from parampilot import AsyncParamPilot, ParamPilot
from parampilot.errors import CompatibilityError, SchemaCompatibilityWarning
from tests.support import TOKEN, availability_payload

EXPECTED_DIGEST = (
    "sha256:a657824fc73aac598a530652348f441b7c3c3f37641d1d6972617487b8b6b1db"
)


def _client_for_payload(
    payload: dict[str, object],
    *,
    schema_compatibility: str = "warn",
) -> tuple[AsyncParamPilot, httpx.AsyncClient]:
    """Build a client whose availability endpoint returns ``payload``.

    Args:
        payload: Availability JSON response.
        schema_compatibility: Digest mismatch policy.

    Returns:
        SDK client and caller-owned HTTPX client.

    """

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return the configured compatibility response.

        Args:
            request: Outbound availability request.

        Returns:
            Successful availability response.

        """
        return httpx.Response(200, json=payload, request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        schema_compatibility=schema_compatibility,
        http_client=http_client,
    )
    return client, http_client


def _sync_client_for_payload(
    payload: dict[str, object],
    *,
    schema_compatibility: str = "warn",
) -> tuple[ParamPilot, httpx.Client]:
    """Build a native sync client returning one availability payload.

    Args:
        payload: Availability JSON response.
        schema_compatibility: Digest mismatch policy.

    Returns:
        Sync SDK client and caller-owned HTTPX client.

    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the configured compatibility response.

        Args:
            request: Outbound availability request.

        Returns:
            Successful availability response.

        """
        return httpx.Response(200, json=payload, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        schema_compatibility=schema_compatibility,  # type: ignore[arg-type]
        http_client=http_client,
    )
    return client, http_client


@pytest.mark.asyncio
async def test_exact_digest_and_required_capability_are_compatible() -> None:
    """Matching major, digest, and capabilities must pass without warnings."""
    client, http_client = _client_for_payload(
        availability_payload(
            capabilities=["experiments.effective"],
            schema_digest=EXPECTED_DIGEST,
        )
    )

    availability = await client.check_compatibility(
        required_capabilities={"experiments.effective"}
    )

    assert availability.api_version == "2.0.0"
    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_missing_capability_is_always_a_hard_error() -> None:
    """An invoked feature's missing stable capability must fail locally."""
    client, http_client = _client_for_payload(
        availability_payload(schema_digest=EXPECTED_DIGEST)
    )

    with pytest.raises(CompatibilityError, match="experiments.effective"):
        await client.check_compatibility(
            required_capabilities={"experiments.effective"}
        )

    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_major_version_mismatch_is_a_hard_compatibility_error() -> None:
    """The SDK must not reinterpret another API major as public v2."""
    client, http_client = _client_for_payload(
        availability_payload(api_version="3.0.0", schema_digest=EXPECTED_DIGEST)
    )

    with pytest.raises(CompatibilityError, match="major"):
        await client.check_compatibility()

    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_same_major_digest_mismatch_warns_by_default() -> None:
    """An additive same-major schema drift must be advisory in default mode."""
    client, http_client = _client_for_payload(
        availability_payload(schema_digest=f"sha256:{'a' * 64}")
    )

    with pytest.warns(SchemaCompatibilityWarning, match="schema digest"):
        await client.check_compatibility()

    await client.close()
    await http_client.aclose()


@pytest.mark.asyncio
async def test_strict_schema_mode_rejects_digest_mismatch() -> None:
    """Strict callers must be able to require the exact generated contract digest."""
    client, http_client = _client_for_payload(
        availability_payload(schema_digest=f"sha256:{'a' * 64}"),
        schema_compatibility="strict",
    )

    with pytest.raises(CompatibilityError, match="schema digest"):
        await client.check_compatibility()

    await client.close()
    await http_client.aclose()


def test_sync_exact_digest_capability_and_cache_are_compatible() -> None:
    """Sync compatibility must validate and cache the same successful payload."""
    requests = 0
    payload = availability_payload(
        capabilities=["experiments.effective"],
        schema_digest=EXPECTED_DIGEST,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        """Count and return the configured compatibility response.

        Args:
            request: Outbound availability request.

        Returns:
            Successful availability response.

        """
        nonlocal requests
        requests += 1
        return httpx.Response(200, json=payload, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    first = client.check_compatibility(required_capabilities={"experiments.effective"})
    second = client.check_compatibility(required_capabilities={"experiments.effective"})

    assert first is second
    assert requests == 1
    client.close()
    http_client.close()


def test_sync_missing_capability_is_a_hard_error() -> None:
    """Sync feature calls must reject missing stable capabilities."""
    client, http_client = _sync_client_for_payload(
        availability_payload(schema_digest=EXPECTED_DIGEST)
    )

    with pytest.raises(CompatibilityError, match="experiments.effective"):
        client.check_compatibility(required_capabilities={"experiments.effective"})

    client.close()
    http_client.close()


def test_sync_strict_schema_mode_rejects_digest_mismatch() -> None:
    """Strict sync callers must require the exact generated schema digest."""
    client, http_client = _sync_client_for_payload(
        availability_payload(schema_digest=f"sha256:{'a' * 64}"),
        schema_compatibility="strict",
    )

    with pytest.raises(CompatibilityError, match="schema digest"):
        client.check_compatibility()

    client.close()
    http_client.close()

"""Transport-level tests for the initial sync and async availability slice."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from parampilot import AsyncParamPilot, ParamPilot
from parampilot.errors import ConfigurationError
from parampilot.models import AvailabilityResponse

TOKEN = "pp_test_secret_token"
SCHEMA_DIGEST = f"sha256:{'a' * 64}"


def _availability_payload() -> dict[str, Any]:
    """Build a representative additive availability response.

    Returns:
        A JSON-compatible response containing all required availability fields.

    """
    return {
        "status": "ok",
        "api_version": "2.0.0",
        "capabilities": ["campaigns", "model-jobs"],
        "schema_digest": SCHEMA_DIGEST,
        "token_expires_at": None,
        "user": {
            "id": "1c4704e7-8261-49a0-a0ef-74dd23fd9165",
            "username": "sdk-user",
            "preferred_language": "en",
        },
        "future_server_field": {"preserved": True},
    }


def _assert_availability_request(request: httpx.Request) -> None:
    """Assert the authenticated v2 compatibility-handshake request.

    Args:
        request: The HTTPX request captured by the mock transport.

    """
    assert request.method == "GET"
    assert request.url == "https://example.test/papi/v2/availability/"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-Agent"].startswith("parampilot/")


@pytest.mark.asyncio
async def test_async_availability_uses_bearer_auth_and_validates_response() -> None:
    """The async client must use its injected pool and return a typed response."""

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a representative availability response.

        Args:
            request: The request issued by the SDK.

        Returns:
            A successful JSON response associated with ``request``.

        """
        _assert_availability_request(request)
        return httpx.Response(200, json=_availability_payload(), request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncParamPilot(
        base_url="https://example.test/",
        token=TOKEN,
        http_client=http_client,
    )

    async with client:
        response = await client.get_availability()

    assert isinstance(response, AvailabilityResponse)
    assert response.schema_digest == SCHEMA_DIGEST
    assert response.model_extra == {"future_server_field": {"preserved": True}}
    assert client.closed is True
    assert http_client.is_closed is False
    await http_client.aclose()


def test_sync_availability_uses_bearer_auth_and_validates_response() -> None:
    """The sync client must use native HTTPX without requiring an event loop."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a representative availability response.

        Args:
            request: The request issued by the SDK.

        Returns:
            A successful JSON response associated with ``request``.

        """
        _assert_availability_request(request)
        return httpx.Response(200, json=_availability_payload(), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test/",
        token=TOKEN,
        http_client=http_client,
    )

    with client:
        response = client.get_availability()

    assert isinstance(response, AvailabilityResponse)
    assert response.user.username == "sdk-user"
    assert client.closed is True
    assert http_client.is_closed is False
    http_client.close()


def test_explicit_token_takes_precedence_over_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit token must override the process environment deterministically."""
    monkeypatch.setenv("PARAMPILOT_API_TOKEN", "environment-token")

    def handler(request: httpx.Request) -> httpx.Response:
        """Verify explicit-token precedence and return availability.

        Args:
            request: The request issued by the SDK.

        Returns:
            A successful JSON response associated with ``request``.

        """
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(200, json=_availability_payload(), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(
        base_url="https://example.test",
        token=TOKEN,
        http_client=http_client,
    )

    client.get_availability()

    client.close()
    http_client.close()


def test_environment_token_is_used_when_explicit_token_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented environment variable must support no-secret-in-code usage."""
    monkeypatch.setenv("PARAMPILOT_API_TOKEN", TOKEN)

    def handler(request: httpx.Request) -> httpx.Response:
        """Verify environment-token loading and return availability.

        Args:
            request: The request issued by the SDK.

        Returns:
            A successful JSON response associated with ``request``.

        """
        _assert_availability_request(request)
        return httpx.Response(200, json=_availability_payload(), request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ParamPilot(base_url="https://example.test", http_client=http_client)

    client.get_availability()

    client.close()
    http_client.close()


def test_missing_token_fails_before_any_network_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing programmatic token must produce actionable local configuration help."""
    monkeypatch.delenv("PARAMPILOT_API_TOKEN", raising=False)
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        """Count any unexpected network access.

        Args:
            request: The unexpected request.

        Returns:
            A response that should never be reached.

        """
        nonlocal requests
        requests += 1
        return httpx.Response(500, request=request)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(ConfigurationError, match="PARAMPILOT_API_TOKEN"):
        ParamPilot(base_url="https://example.test", http_client=http_client)

    assert requests == 0
    http_client.close()


def test_client_repr_and_configuration_errors_never_expose_token() -> None:
    """Secrets must stay redacted from common diagnostic representations."""
    client = ParamPilot(base_url="https://example.test", token=TOKEN)

    assert TOKEN not in repr(client)
    assert "[REDACTED]" not in repr(client)

    client.close()


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "example.test",
        "ftp://example.test",
        "https://example.test/path?secret=value",
        "https://example.test/path#fragment",
    ],
)
def test_invalid_base_urls_fail_locally(base_url: str) -> None:
    """Only absolute HTTP origins and optional path prefixes are accepted.

    Args:
        base_url: The invalid URL candidate under test.

    """
    with pytest.raises(ConfigurationError, match="base_url"):
        ParamPilot(base_url=base_url, token=TOKEN)

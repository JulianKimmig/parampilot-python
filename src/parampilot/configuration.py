"""Validated, secret-safe client configuration shared by both transports."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from math import isfinite
from typing import Literal
from urllib.parse import urlsplit

from parampilot._version import __version__
from parampilot.errors import ConfigurationError

TOKEN_ENVIRONMENT_VARIABLE = "PARAMPILOT_API_TOKEN"  # noqa: S105


@dataclass(frozen=True, slots=True)
class ClientConfiguration:
    """Normalized connection settings without secret-bearing representations.

    Args:
        base_url: Absolute HTTP(S) URL for a ParamPilot deployment.
        token: Programmatic bearer token. When omitted, the environment is used.
        timeout: Per-request timeout in seconds.
        max_retries: Retry count for safe/idempotent requests.
        retry_backoff: Base exponential retry delay in seconds.
        schema_compatibility: Same-major schema-digest mismatch policy.

    """

    base_url: str
    timeout: float = 30.0
    max_retries: int = 2
    retry_backoff: float = 0.25
    schema_compatibility: Literal["warn", "strict", "ignore"] = "warn"
    _token: str = field(default="", repr=False)

    @classmethod
    def create(
        cls,
        *,
        base_url: str,
        token: str | None,
        timeout: float,
        max_retries: int = 2,
        retry_backoff: float = 0.25,
        schema_compatibility: Literal["warn", "strict", "ignore"] = "warn",
    ) -> ClientConfiguration:
        """Validate and normalize caller-supplied client settings.

        Args:
            base_url: Absolute deployment URL, optionally with a path prefix.
            token: Explicit token or ``None`` to read the documented environment.
            timeout: Positive request timeout in seconds.
            max_retries: Nonnegative retry count for safe operations.
            retry_backoff: Nonnegative base delay between retry attempts.
            schema_compatibility: Same-major schema-digest mismatch policy.

        Returns:
            A validated immutable configuration object.

        Raises:
            ConfigurationError: If the URL, token, or timeout is invalid.

        """
        normalized_url = _normalize_base_url(base_url)
        resolved_token = _resolve_token(token)
        if not isfinite(timeout) or timeout <= 0:
            raise ConfigurationError("timeout must be greater than zero seconds")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 0 <= max_retries <= 10
        ):
            raise ConfigurationError("max_retries must be an integer from 0 to 10")
        if not isfinite(retry_backoff) or retry_backoff < 0:
            raise ConfigurationError("retry_backoff must be a nonnegative number")
        if schema_compatibility not in {"warn", "strict", "ignore"}:
            raise ConfigurationError(
                "schema_compatibility must be 'warn', 'strict', or 'ignore'"
            )
        return cls(
            base_url=normalized_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            schema_compatibility=schema_compatibility,
            _token=resolved_token,
        )

    @property
    def token(self) -> str:
        """Return the token for authenticated transport use.

        Returns:
            The validated programmatic bearer token.

        """
        return self._token

    def endpoint(self, path: str) -> str:
        """Join a rooted public API path to the configured deployment URL.

        Args:
            path: Rooted public API path beginning with ``/``.

        Returns:
            An absolute request URL.

        Raises:
            ConfigurationError: If ``path`` is not rooted.

        """
        if not path.startswith("/"):
            raise ConfigurationError("API request path must begin with '/'")
        return f"{self.base_url}{path}"

    def request_headers(self, *, accept: str = "application/json") -> dict[str, str]:
        """Build the fixed authenticated headers for one API request.

        Args:
            accept: Requested response media type.

        Returns:
            A new header dictionary containing bearer auth and SDK identity.

        """
        return {
            "Accept": accept,
            "Authorization": f"Bearer {self._token}",
            "User-Agent": f"parampilot/{__version__}",
        }

    def redact(self, value: str) -> str:
        """Remove the configured token from a diagnostic string.

        Args:
            value: Potentially secret-bearing diagnostic.

        Returns:
            String with exact credential occurrences removed.

        """
        return value.replace(self._token, "[REDACTED]")


def _normalize_base_url(base_url: str) -> str:
    """Normalize and validate a deployment base URL.

    Args:
        base_url: User-supplied URL candidate.

    Returns:
        The URL without trailing slashes.

    Raises:
        ConfigurationError: If credentials, query, fragment, or invalid origin exist.

    """
    candidate = base_url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError("base_url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ConfigurationError("base_url must not contain a query or fragment")
    return candidate.rstrip("/")


def _resolve_token(token: str | None) -> str:
    """Resolve explicit-over-environment token precedence.

    Args:
        token: Explicit programmatic token or ``None``.

    Returns:
        A non-empty token value.

    Raises:
        ConfigurationError: If neither source contains a usable token.

    """
    resolved = token if token is not None else os.getenv(TOKEN_ENVIRONMENT_VARIABLE)
    if resolved is None or not resolved.strip():
        raise ConfigurationError(
            "A ParamPilot programmatic API token is required. Pass token=... or "
            f"set {TOKEN_ENVIRONMENT_VARIABLE}."
        )
    return resolved

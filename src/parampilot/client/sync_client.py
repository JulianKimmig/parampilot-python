"""Synchronous public client with native typed resources and compatibility."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from threading import Lock
from typing import Any

import httpx
from pydantic import ValidationError

from parampilot.compatibility import (
    SchemaCompatibility,
    require_api_major,
    validate_compatibility,
)
from parampilot.configuration import ClientConfiguration
from parampilot.errors import ResponseDecodeError, ResponseValidationError
from parampilot.models import AvailabilityResponse
from parampilot.operations import operation
from parampilot.raw_response import sanitized_raw_response
from parampilot.serialization import json_value
from parampilot.sync_resources.campaign_access import SyncCampaignAccessResource
from parampilot.sync_resources.campaign_transfer_links import (
    SyncCampaignTransferLinksResource,
)
from parampilot.sync_resources.campaigns import SyncCampaignsResource
from parampilot.sync_resources.experiments import SyncExperimentsResource
from parampilot.sync_resources.model_artifacts import SyncModelArtifactsResource
from parampilot.sync_resources.model_jobs import SyncModelJobsResource
from parampilot.sync_workflows import Workflows
from parampilot.transport import SyncTransport


class ParamPilot:
    """Synchronous entry point for the complete ParamPilot public API.

    Args:
        base_url: Absolute URL of the ParamPilot deployment.
        token: Programmatic token or ``None`` to use ``PARAMPILOT_API_TOKEN``.
        timeout: Positive per-request timeout in seconds.
        max_retries: Retry count for safe reads and keyed mutations.
        retry_backoff: Base deterministic retry delay in seconds.
        schema_compatibility: ``warn``, ``strict``, or ``ignore`` digest policy.
        http_client: Optional caller-owned synchronous HTTPX client.

    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_backoff: float = 0.25,
        schema_compatibility: SchemaCompatibility = "warn",
        http_client: httpx.Client | None = None,
    ) -> None:
        """Create a native synchronous API client and reusable resources.

        Args:
            base_url: Absolute URL of the ParamPilot deployment.
            token: Programmatic token or ``None`` to use the environment.
            timeout: Positive per-request timeout in seconds.
            max_retries: Retry count for safe reads and keyed mutations.
            retry_backoff: Base deterministic retry delay in seconds.
            schema_compatibility: Same-major schema-digest mismatch policy.
            http_client: Optional caller-owned synchronous HTTPX client.

        """
        self._configuration = ClientConfiguration.create(
            base_url=base_url,
            token=token,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            schema_compatibility=schema_compatibility,
        )
        self._transport = SyncTransport(self._configuration, http_client)
        self._availability_cache: AvailabilityResponse | None = None
        self._availability_lock = Lock()
        self.campaigns = SyncCampaignsResource(
            self._transport,
            self._check_capabilities,
        )
        self.campaign_access = SyncCampaignAccessResource(
            self._transport,
            self._check_capabilities,
        )
        self.campaign_transfer_links = SyncCampaignTransferLinksResource(
            self._transport,
            self._check_capabilities,
        )
        self.experiments = SyncExperimentsResource(
            self._transport,
            self._check_capabilities,
        )
        self.model_jobs = SyncModelJobsResource(
            self._transport,
            self._check_capabilities,
        )
        self.model_artifacts = SyncModelArtifactsResource(
            self._transport,
            self._check_capabilities,
        )
        self.workflows = Workflows(self.experiments, self.model_jobs)

    @property
    def closed(self) -> bool:
        """Report whether this SDK client has been closed.

        Returns:
            The SDK transport's closed state.

        """
        return self._transport.closed

    def _fetch_availability(self, *, check_major: bool) -> AvailabilityResponse:
        """Fetch and validate the availability wire response.

        Args:
            check_major: Raise a compatibility error before generated coercion.

        Returns:
            Validated availability response.

        Raises:
            ResponseDecodeError: If successful JSON cannot be decoded.
            ResponseValidationError: If v2 availability fields are invalid.

        """
        metadata = operation("getAvailability")
        response = self._transport.request_operation(metadata, metadata.path())
        request_id = response.headers.get("X-Request-ID")
        try:
            payload = response.json()
        except ValueError as error:
            raise ResponseDecodeError(
                "The ParamPilot availability response was not valid JSON",
                operation_id=metadata.operation_id,
                request_id=request_id,
            ) from error
        if not isinstance(payload, dict):
            raise ResponseValidationError(
                "The ParamPilot availability response was not a JSON object",
                operation_id=metadata.operation_id,
                request_id=request_id,
            )
        if check_major:
            require_api_major(payload)
        try:
            return AvailabilityResponse.model_validate(payload)
        except ValidationError as error:
            raise ResponseValidationError(
                "The ParamPilot availability response violated the public contract",
                operation_id=metadata.operation_id,
                request_id=request_id,
            ) from error

    def get_availability(self) -> AvailabilityResponse:
        """Fetch the authenticated server compatibility handshake.

        Returns:
            Validated API version, capabilities, digest, token, and user metadata.

        """
        return self._fetch_availability(check_major=False)

    def check_compatibility(
        self,
        *,
        required_capabilities: Collection[str] = (),
        refresh: bool = False,
    ) -> AvailabilityResponse:
        """Validate API major, required capabilities, and schema digest.

        Args:
            required_capabilities: Stable capabilities needed by the caller.
            refresh: Bypass the cached handshake when true.

        Returns:
            Validated compatible availability response.

        Raises:
            CompatibilityError: For another API major, missing capabilities,
                or a strict schema-digest mismatch.

        """
        with self._availability_lock:
            if refresh or self._availability_cache is None:
                self._availability_cache = self._fetch_availability(check_major=True)
            availability = self._availability_cache
        validate_compatibility(
            availability,
            required_capabilities=required_capabilities,
            schema_compatibility=self._configuration.schema_compatibility,
        )
        return availability

    def _check_capabilities(self, values: Collection[str]) -> object:
        """Adapt the public compatibility call for resource dependencies.

        Args:
            values: Required stable feature capabilities.

        Returns:
            Validated availability response as an opaque dependency value.

        """
        return self.check_compatibility(required_capabilities=values)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        accept: str = "*/*",
    ) -> httpx.Response:
        """Issue an explicitly untyped request within the public-v2 boundary.

        Args:
            method: HTTP method.
            path: Rooted path beneath ``/papi/v2/``; absolute URLs are rejected.
            params: Optional typed query mapping.
            json: Optional JSON-compatible request body.
            headers: Optional headers except SDK-managed auth/host/user-agent.
            accept: Explicit response media type.

        Returns:
            Successful raw HTTPX response.

        """
        response = self._transport.request_raw(
            method,
            path,
            params=params,
            json_body=json_value(json) if json is not None else None,
            headers=headers,
            accept=accept,
        )
        return sanitized_raw_response(response)

    def close(self) -> None:
        """Close resources owned by this SDK client."""
        self._transport.close()

    def __enter__(self) -> ParamPilot:
        """Enter a reusable synchronous client context.

        Returns:
            This client instance.

        """
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """Close owned resources when leaving a context.

        Args:
            exc_type: Active exception type, if any.
            exc_value: Active exception value, if any.
            traceback: Active traceback, if any.

        """
        self.close()

    def __repr__(self) -> str:
        """Return a token-free diagnostic representation.

        Returns:
            A representation containing only the base URL and closed state.

        """
        return (
            f"ParamPilot(base_url={self._configuration.base_url!r}, "
            f"closed={self.closed!r})"
        )

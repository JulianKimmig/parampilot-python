"""Public, secret-safe exception hierarchy for the ParamPilot SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from parampilot.models import PublicModelJobObservation


class ParamPilotError(Exception):
    """Base class for every SDK-defined failure."""


class ConfigurationError(ParamPilotError):
    """Raised when local client configuration is invalid or incomplete."""


class CompatibilityError(ParamPilotError):
    """Raised for an incompatible API major, capability, or strict digest."""


class SchemaCompatibilityWarning(UserWarning):
    """Warn that a same-major server schema differs from the generated SDK."""


class TransportError(ParamPilotError):
    """Raised when HTTPX cannot complete an API request.

    Args:
        message: Privacy-safe transport diagnostic.
        operation_id: Stable operation identifier when known.

    """

    def __init__(self, message: str, operation_id: str | None = None) -> None:
        """Initialize a transport failure.

        Args:
            message: Privacy-safe transport diagnostic.
            operation_id: Stable operation identifier when known.

        """
        self.operation_id = operation_id
        super().__init__(message)


class ResponseValidationError(ParamPilotError):
    """Raised when a successful response violates its generated contract.

    Args:
        message: Privacy-safe validation diagnostic.
        operation_id: Stable operation identifier when known.
        request_id: Optional safe server correlation identifier.

    """

    def __init__(
        self,
        message: str,
        *,
        operation_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Initialize a response-contract failure.

        Args:
            message: Privacy-safe validation diagnostic.
            operation_id: Stable operation identifier when known.
            request_id: Optional safe server correlation identifier.

        """
        self.operation_id = operation_id
        self.request_id = request_id
        super().__init__(message)


class ResponseDecodeError(ResponseValidationError):
    """Raised when a response expected to be JSON cannot be decoded."""


class ParamPilotHTTPError(ParamPilotError):
    """Canonical unsuccessful HTTP response with privacy-safe context.

    Args:
        status_code: HTTP response status code.
        request_id: Optional safe request correlation identifier.
        code: Stable machine-readable server error code.
        message: Privacy-safe server explanation.
        retryable: Whether the server classifies a later retry as meaningful.
        issues: Structured privacy-safe validation issues.
        context: Operation-specific privacy-safe recovery context.
        operation_id: Stable operation identifier when known.
        retry_after: Optional nonnegative retry delay in seconds.

    """

    def __init__(
        self,
        status_code: int,
        request_id: str | None = None,
        *,
        code: str = "http_error",
        message: str | None = None,
        retryable: bool = False,
        issues: Sequence[Mapping[str, Any]] = (),
        context: Mapping[str, Any] | None = None,
        operation_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Initialize one safe canonical HTTP failure.

        Args:
            status_code: HTTP response status code.
            request_id: Optional safe request correlation identifier.
            code: Stable machine-readable server error code.
            message: Privacy-safe server explanation.
            retryable: Whether the server classifies a later retry as meaningful.
            issues: Structured privacy-safe validation issues.
            context: Operation-specific privacy-safe recovery context.
            operation_id: Stable operation identifier when known.
            retry_after: Optional nonnegative retry delay in seconds.

        """
        self.status_code = status_code
        self.request_id = request_id
        self.code = code
        self.retryable = retryable
        self.issues = tuple(dict(issue) for issue in issues)
        self.context = dict(context or {})
        self.operation_id = operation_id
        self.retry_after = retry_after
        diagnostic = message or f"ParamPilot API request failed with HTTP {status_code}"
        if request_id:
            diagnostic = f"{diagnostic} (request_id={request_id})"
        super().__init__(diagnostic)


class InvalidRequestError(ParamPilotHTTPError):
    """Raised for malformed requests, cursors, or idempotency keys."""


class AuthenticationError(ParamPilotHTTPError):
    """Raised when the programmatic bearer token is rejected."""


class PermissionDeniedError(ParamPilotHTTPError):
    """Raised when the authenticated principal lacks required access."""


class NotFoundError(ParamPilotHTTPError):
    """Raised when an authorized public resource is unavailable."""


class ConflictError(ParamPilotHTTPError):
    """Raised when current server state conflicts with the request."""


class IdempotencyError(ConflictError):
    """Raised for in-progress or fingerprint-conflicting idempotency keys."""


class TrainingRequiredError(ConflictError):
    """Raised when Ask, Predict, or an artifact requires explicit training."""


class JobError(ConflictError):
    """Raised for incomplete, failed, canceled, or noncancelable jobs."""


class RevisionConflictError(ParamPilotHTTPError):
    """Raised when an ``If-Match`` resource revision is stale."""


class PayloadTooLargeError(ParamPilotHTTPError):
    """Raised when an upload exceeds the public request bound."""


class UnsupportedMediaTypeError(ParamPilotHTTPError):
    """Raised when an upload or response media type is unsupported."""


class RequestValidationError(ParamPilotHTTPError):
    """Raised for structured request or row validation failures."""


class LockedError(ParamPilotHTTPError):
    """Raised when a model or campaign operation is currently locked."""


class PreconditionRequiredError(ParamPilotHTTPError):
    """Raised when a required optimistic-concurrency header is absent."""


class RateLimitError(ParamPilotHTTPError):
    """Raised when the caller exceeds a server-owned request limit."""


class ServerError(ParamPilotHTTPError):
    """Raised for declared internal, unavailable, or upstream failures."""


class WorkflowError(ParamPilotError):
    """Base failure for explicit multi-operation workflows."""


class JobWaitError(ParamPilotError):
    """Base local waiting failure with reconstructable job recovery context.

    Args:
        message: Privacy-safe waiter diagnostic.
        campaign_id: Public campaign UUID.
        job_id: Public model-job UUID.
        last_observation: Last validated server observation, if any.

    """

    def __init__(
        self,
        message: str,
        *,
        campaign_id: UUID,
        job_id: UUID,
        last_observation: PublicModelJobObservation | None,
    ) -> None:
        """Initialize a safe recoverable waiting failure.

        Args:
            message: Privacy-safe waiter diagnostic.
            campaign_id: Public campaign UUID.
            job_id: Public model-job UUID.
            last_observation: Last validated server observation, if any.

        """
        self.campaign_id = campaign_id
        self.job_id = job_id
        self.last_observation = last_observation
        super().__init__(message)


class JobFailedError(JobWaitError):
    """Raised when a waited remote model job reaches ``failed``."""


class JobCanceledError(JobWaitError):
    """Raised when a waited remote model job reaches ``canceled``."""


class JobWaitTimeoutError(JobWaitError):
    """Raised when local monotonic waiting expires without remote cancellation."""


class JobPollingError(JobWaitError):
    """Wrap a typed polling/result failure while retaining the last observation."""


class JobAuthenticationError(JobPollingError):
    """Wrap authentication loss encountered while observing or reading a job."""


class JobCompatibilityError(JobPollingError):
    """Wrap server compatibility loss encountered while waiting for a job."""


class JobProgressCallbackError(JobWaitError):
    """Wrap a caller progress-callback failure without implicit cancellation."""

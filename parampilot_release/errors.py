"""Typed local failures for release extraction and public-tree auditing."""


class ReleasePreparationError(RuntimeError):
    """Base class for a local release-candidate preparation failure."""


class PublicExtractionError(ReleasePreparationError):
    """Raised when private-source identity or extraction safety is invalid."""


class PublicAuditError(ReleasePreparationError):
    """Raised when a candidate public tree violates integrity or safety rules."""


__all__ = [
    "PublicAuditError",
    "PublicExtractionError",
    "ReleasePreparationError",
]

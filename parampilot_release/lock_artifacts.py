"""Fail-closed validation for public-registry artifacts in uv lock entries."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from parampilot_release.errors import PublicAuditError

PYPI_ARTIFACT_HOST = "files.pythonhosted.org"
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
INVALID_ARTIFACT_MESSAGE = (
    "public dependency lock contains invalid registry artifact metadata"
)


def validate_registry_artifacts(package: dict[str, Any]) -> None:
    """Require every declared locked artifact to be hashed and PyPI-hosted.

    Args:
        package: Parsed registry-backed uv lock package entry.

    Raises:
        PublicAuditError: If artifact shape, URL, digest, or size is unsafe.

    """
    artifacts: list[Any] = []
    if "sdist" in package:
        artifacts.append(package["sdist"])
    if "wheels" in package:
        wheels = package["wheels"]
        if not isinstance(wheels, list):
            _raise_invalid_artifact()
        artifacts.extend(wheels)
    if not artifacts:
        _raise_invalid_artifact()
    for artifact in artifacts:
        _validate_artifact(artifact)


def _validate_artifact(value: Any) -> None:
    """Validate one PyPI artifact mapping without exposing unsafe values.

    Args:
        value: Candidate parsed sdist or wheel metadata.

    Raises:
        PublicAuditError: If required provenance metadata is malformed.

    """
    if not isinstance(value, dict):
        _raise_invalid_artifact()
    url = value.get("url")
    digest = value.get("hash")
    size = value.get("size")
    if not isinstance(url, str) or not isinstance(digest, str):
        _raise_invalid_artifact()
    if not url.isascii() or any(
        ord(character) < 0x21 or ord(character) == 0x7F for character in url
    ):
        _raise_invalid_artifact()
    if not SHA256_PATTERN.fullmatch(digest):
        _raise_invalid_artifact()
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        _raise_invalid_artifact()
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise PublicAuditError(INVALID_ARTIFACT_MESSAGE) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != PYPI_ARTIFACT_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/packages/")
        or parsed.path == "/packages/"
    ):
        _raise_invalid_artifact()


def _raise_invalid_artifact() -> None:
    """Raise the stable registry-artifact validation failure.

    Raises:
        PublicAuditError: Always.

    """
    raise PublicAuditError(INVALID_ARTIFACT_MESSAGE)


__all__ = ["validate_registry_artifacts"]

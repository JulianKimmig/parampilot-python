"""Credential-free HTTPX response copies for the advanced request escape hatch."""

from __future__ import annotations

import httpx

SENSITIVE_REQUEST_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization"}
)


def sanitized_raw_response(response: httpx.Response) -> httpx.Response:
    """Copy a buffered response without its authenticated request object.

    Args:
        response: Successful buffered response returned by the SDK transport.

    Returns:
        Independent HTTPX response whose request omits credentials and body.

    """
    request_headers = {
        name: value
        for name, value in response.request.headers.items()
        if name.lower() not in SENSITIVE_REQUEST_HEADERS
    }
    safe_request = httpx.Request(
        response.request.method,
        response.request.url,
        headers=request_headers,
    )
    return httpx.Response(
        response.status_code,
        headers=response.headers,
        content=response.content,
        request=safe_request,
    )

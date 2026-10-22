"""Error helpers shared by the write paths."""

import asyncio

import aiohttp

# Network-level failures that may succeed when the request is sent again.
TRANSPORT_ERRORS = (
    asyncio.TimeoutError,
    aiohttp.client_exceptions.ServerDisconnectedError,
    aiohttp.client_exceptions.ClientPayloadError,
    aiohttp.client_exceptions.ClientOSError,
)


def is_transient_error(exc: BaseException) -> bool:
    """True for errors worth retrying: transport errors, 429 and 5xx responses.

    Any other HTTP status (for example 400) and response validation errors are
    deterministic, so sending the same request again cannot help.
    """
    if isinstance(exc, TRANSPORT_ERRORS):
        return True
    status = getattr(exc, "status", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def summarize_error(exc: BaseException) -> str:
    """One-line description of an error, without HTTP headers or body."""
    status = getattr(exc, "status", None)
    if status is not None:
        reason = getattr(exc, "reason", None)
        detail = " ".join(str(part) for part in (status, reason) if part)
        return f"{type(exc).__name__} ({detail})"
    lines = str(exc).strip().splitlines()
    return f"{type(exc).__name__}: {lines[0]}" if lines else type(exc).__name__

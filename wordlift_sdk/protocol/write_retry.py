"""Retry policy shared by the entity write queues."""

import asyncio
import logging

import aiohttp
import wordlift_client
from tenacity import (
    after_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

# Transient failures only. A 400 or a response validation error is
# deterministic, so it is not retried.
RETRYABLE_WRITE_ERRORS = (
    asyncio.TimeoutError
    | aiohttp.client_exceptions.ServerDisconnectedError
    | aiohttp.client_exceptions.ClientConnectorError
    | aiohttp.client_exceptions.ClientPayloadError
    | aiohttp.client_exceptions.ClientConnectorDNSError
    | wordlift_client.exceptions.ServiceException
    | aiohttp.client_exceptions.ClientOSError
)

WRITE_ATTEMPTS = 5


def retry_write(logger: logging.Logger):
    """Retry a write up to WRITE_ATTEMPTS times, then re-raise the last error.

    Waits grow exponentially from 2s up to 30s, with jitter, so a short server
    error burst is ridden out without hammering the API.
    """
    return retry(
        stop=stop_after_attempt(WRITE_ATTEMPTS),
        retry=retry_if_exception_type(RETRYABLE_WRITE_ERRORS),
        wait=wait_exponential_jitter(initial=2, max=30),
        after=after_log(logger, logging.WARNING),
        reraise=True,
    )

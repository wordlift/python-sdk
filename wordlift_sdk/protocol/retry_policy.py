"""Retry policy for WordLift API calls, applied as a decorator."""

import logging
from typing import Callable, TypeVar

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .errors import is_transient_error, summarize_error

RETRY_ATTEMPTS = 5

F = TypeVar("F", bound=Callable)


def retry_transient(logger: logging.Logger) -> Callable[[F], F]:
    """Retry transient failures up to RETRY_ATTEMPTS times, then re-raise.

    Waits grow exponentially from 2s up to 30s, with jitter. Each retry logs
    one warning line; the final error propagates to the caller, which reports
    it once.
    """

    def log_retry(state: RetryCallState) -> None:
        logger.warning(
            "%s failed (%s); attempt %d of %d, retrying in %.1fs",
            getattr(state.fn, "__qualname__", state.fn),
            summarize_error(state.outcome.exception()),
            state.attempt_number,
            RETRY_ATTEMPTS,
            state.upcoming_sleep,
        )

    return retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        retry=retry_if_exception(is_transient_error),
        wait=wait_exponential_jitter(initial=2, max=30),
        before_sleep=log_retry,
        reraise=True,
    )

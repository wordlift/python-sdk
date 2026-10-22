import asyncio
import logging

import pydantic
import pytest
import wordlift_client

from wordlift_sdk.protocol.errors import is_transient_error, summarize_error
from wordlift_sdk.protocol.retry_policy import RETRY_ATTEMPTS, retry_transient

logger = logging.getLogger(__name__)


def _api_error(status: int, reason: str | None = None) -> Exception:
    return wordlift_client.exceptions.ApiException(status=status, reason=reason)


def _validation_error() -> Exception:
    try:
        pydantic.TypeAdapter(int).validate_python("not a number")
    except pydantic.ValidationError as exc:
        return exc
    raise AssertionError("expected a validation error")


@pytest.mark.parametrize(
    "error",
    [
        asyncio.TimeoutError(),
        _api_error(429, "Too Many Requests"),
        _api_error(500, "Internal Server Error"),
        _api_error(503),
    ],
)
def test_transient_errors_are_retried(error):
    assert is_transient_error(error)


@pytest.mark.parametrize(
    "error",
    [
        _api_error(400, "Bad Request"),
        _api_error(404),
        _validation_error(),
        RuntimeError("boom"),
    ],
)
def test_deterministic_errors_are_not_retried(error):
    assert not is_transient_error(error)


def test_summarize_error_drops_http_details():
    error = wordlift_client.exceptions.ServiceException(
        status=500, reason="Internal Server Error"
    )

    assert summarize_error(error) == "ServiceException (500 Internal Server Error)"
    assert summarize_error(_api_error(503)) == "ApiException (503)"
    assert summarize_error(RuntimeError("first\nsecond")) == "RuntimeError: first"
    assert summarize_error(RuntimeError()) == "RuntimeError"


class _Flaky:
    def __init__(self, *errors):
        self.calls = 0
        self._errors = list(errors)

    @retry_transient(logger)
    async def call(self) -> str:
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return "ok"


@pytest.mark.asyncio
async def test_retry_transient_logs_one_line_per_retry(no_retry_wait, caplog):
    no_retry_wait(_Flaky.call)
    flaky = _Flaky(_api_error(500, "Internal Server Error"))

    with caplog.at_level(logging.WARNING, logger=__name__):
        assert await flaky.call() == "ok"

    assert flaky.calls == 2
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    message = caplog.records[0].getMessage()
    assert "_Flaky.call failed (ApiException (500 Internal Server Error))" in message
    assert f"attempt 1 of {RETRY_ATTEMPTS}" in message


@pytest.mark.asyncio
async def test_retry_transient_reraises_original_error_after_last_attempt(
    no_retry_wait,
):
    no_retry_wait(_Flaky.call)
    flaky = _Flaky(*[_api_error(429)] * RETRY_ATTEMPTS)

    with pytest.raises(wordlift_client.exceptions.ApiException):
        await flaky.call()

    assert flaky.calls == RETRY_ATTEMPTS


@pytest.mark.asyncio
async def test_retry_transient_does_not_retry_deterministic_errors(no_retry_wait):
    no_retry_wait(_Flaky.call)
    flaky = _Flaky(_validation_error())

    with pytest.raises(pydantic.ValidationError):
        await flaky.call()

    assert flaky.calls == 1

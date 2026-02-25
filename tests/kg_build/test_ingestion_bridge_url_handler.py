from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from wordlift_sdk.ingestion.errors import LoaderRuntimeError
from wordlift_sdk.ingestion.loaders import PlaywrightLoaderAdapter
from wordlift_sdk.url_source import Url
from wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler import (
    IngestionWebPageScrapeUrlHandler,
    _format_failure_diagnostics,
    _sanitize_url,
    _sanitize_text,
    _truncate,
)


@pytest.mark.asyncio
async def test_ingestion_bridge_handler_calls_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = AsyncMock()
    provider = MagicMock()
    provider.get_value.side_effect = lambda key, default=None: {
        "WORDLIFT_KEY": "key",
        "API_URL": "https://api.wordlift.io",
        "INGEST_LOADER": "web_scrape_api",
    }.get(key, default)

    handler = IngestionWebPageScrapeUrlHandler(
        context=MagicMock(),
        configuration_provider=provider,
        web_page_scrape_callback=callback,
    )

    monkeypatch.setattr(
        "wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler.run_ingestion",
        lambda settings: SimpleNamespace(
            pages=[
                SimpleNamespace(
                    item_id="id",
                    url="https://example.com",
                    final_url="https://example.com/final",
                    status_code=200,
                    html="<html>ok</html>",
                    fetch_meta={"backend": "web_scrape_api"},
                )
            ],
            events=[],
        ),
    )

    await handler(Url(value="https://example.com", iri="https://example.com/id"))

    callback.callback.assert_awaited_once()
    args, kwargs = callback.callback.call_args
    response = args[0]
    assert response.web_page.url == "https://example.com/final"
    assert response.web_page.html == "<html>ok</html>"
    assert kwargs["existing_web_page_id"] == "https://example.com/id"


@pytest.mark.asyncio
async def test_ingestion_bridge_handler_raises_on_failed_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = AsyncMock()
    provider = MagicMock()
    provider.get_value.side_effect = lambda key, default=None: {
        "WORDLIFT_KEY": "key",
        "API_URL": "https://api.wordlift.io",
    }.get(key, default)

    handler = IngestionWebPageScrapeUrlHandler(
        context=MagicMock(),
        configuration_provider=provider,
        web_page_scrape_callback=callback,
    )

    monkeypatch.setattr(
        "wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler.run_ingestion",
        lambda settings: SimpleNamespace(
            pages=[],
            events=[
                {
                    "event": "ingest.item_failed",
                    "code": "INGEST_LOAD_REMOTE_API_ERROR",
                    "message": "failed",
                }
            ],
        ),
    )

    with pytest.raises(RuntimeError, match="INGEST_LOAD_REMOTE_API_ERROR"):
        await handler(Url(value="https://example.com"))


@pytest.mark.asyncio
async def test_ingestion_bridge_handler_surfaces_failed_meta_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    callback = AsyncMock()
    provider = MagicMock()
    provider.get_value.side_effect = lambda key, default=None: {
        "WORDLIFT_KEY": "key",
        "API_URL": "https://api.wordlift.io",
    }.get(key, default)

    handler = IngestionWebPageScrapeUrlHandler(
        context=MagicMock(),
        configuration_provider=provider,
        web_page_scrape_callback=callback,
    )
    caplog.set_level("ERROR")

    monkeypatch.setattr(
        "wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler.run_ingestion",
        lambda settings: SimpleNamespace(
            pages=[],
            events=[
                {
                    "event": "ingest.item_failed",
                    "code": "INGEST_LOAD_BROWSER_ERROR",
                    "message": "Playwright loader failed for https://example.com",
                    "meta": {
                        "phase": "navigate",
                        "root_exception_type": "TimeoutError",
                        "root_exception_message": "Navigation timeout",
                        "url": "https://example.com/path?token=secret123&id=1",
                        "wait_until": "networkidle",
                        "timeout_ms": 30000,
                        "headless": True,
                    },
                }
            ],
        ),
    )

    with pytest.raises(RuntimeError) as exc:
        await handler(Url(value="https://example.com"))

    text = str(exc.value)
    assert (
        "Ingestion loader failed for https://example.com: INGEST_LOAD_BROWSER_ERROR Playwright loader failed for https://example.com"
        in text
    )
    assert "diagnostics=" in text
    diagnostics = json.loads(text.split("diagnostics=", 1)[1])
    assert diagnostics["phase"] == "navigate"
    assert diagnostics["root_exception_type"] == "TimeoutError"
    assert diagnostics["root_exception_message"] == "Navigation timeout"
    assert diagnostics["wait_until"] == "networkidle"
    assert diagnostics["timeout_ms"] == 30000
    assert diagnostics["headless"] is True
    assert diagnostics["url"] == "https://example.com/path?token=%5BREDACTED%5D&id=1"
    assert any("diagnostics=" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_ingestion_bridge_handler_meta_fallback_keeps_old_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = AsyncMock()
    provider = MagicMock()
    provider.get_value.side_effect = lambda key, default=None: {
        "WORDLIFT_KEY": "key",
        "API_URL": "https://api.wordlift.io",
    }.get(key, default)

    handler = IngestionWebPageScrapeUrlHandler(
        context=MagicMock(),
        configuration_provider=provider,
        web_page_scrape_callback=callback,
    )

    monkeypatch.setattr(
        "wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler.run_ingestion",
        lambda settings: SimpleNamespace(
            pages=[],
            events=[
                {
                    "event": "ingest.item_failed",
                    "code": "INGEST_LOAD_REMOTE_API_ERROR",
                    "message": "failed",
                    "meta": {},
                }
            ],
        ),
    )

    with pytest.raises(RuntimeError) as exc:
        await handler(Url(value="https://example.com"))
    assert (
        str(exc.value)
        == "Ingestion loader failed for https://example.com: INGEST_LOAD_REMOTE_API_ERROR failed"
    )


@pytest.mark.asyncio
async def test_ingestion_bridge_handler_truncates_diagnostics_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = AsyncMock()
    provider = MagicMock()
    provider.get_value.side_effect = lambda key, default=None: {
        "WORDLIFT_KEY": "key",
        "API_URL": "https://api.wordlift.io",
    }.get(key, default)

    handler = IngestionWebPageScrapeUrlHandler(
        context=MagicMock(),
        configuration_provider=provider,
        web_page_scrape_callback=callback,
    )

    long_message = "token=abc123 " + ("x" * 10000)
    monkeypatch.setattr(
        "wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler.run_ingestion",
        lambda settings: SimpleNamespace(
            pages=[],
            events=[
                {
                    "event": "ingest.item_failed",
                    "code": "INGEST_LOAD_BROWSER_ERROR",
                    "message": "Playwright loader failed for https://example.com",
                    "meta": {
                        "phase": "content",
                        "root_exception_type": "RuntimeError",
                        "root_exception_message": long_message,
                        "url": "https://example.com/path?api_key=abc123",
                        "wait_until": "load",
                        "timeout_ms": 30000,
                        "headless": False,
                    },
                }
            ],
        ),
    )

    with pytest.raises(RuntimeError) as exc:
        await handler(Url(value="https://example.com"))
    diagnostics_str = str(exc.value).split("diagnostics=", 1)[1]
    assert len(diagnostics_str) <= 3072
    diagnostics = json.loads(diagnostics_str)
    assert diagnostics["root_exception_type"] == "RuntimeError"
    assert "[REDACTED]" in diagnostics["root_exception_message"]
    assert diagnostics["url"].endswith("api_key=%5BREDACTED%5D")


@pytest.mark.asyncio
async def test_ingestion_bridge_handler_shows_orchestrator_failure_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = AsyncMock()
    provider = MagicMock()
    provider.get_value.side_effect = lambda key, default=None: {
        "WORDLIFT_KEY": "key",
        "API_URL": "https://api.wordlift.io",
        "INGEST_LOADER": "playwright",
        "INGEST_RETRY_ATTEMPTS": 1,
    }.get(key, default)

    handler = IngestionWebPageScrapeUrlHandler(
        context=MagicMock(),
        configuration_provider=provider,
        web_page_scrape_callback=callback,
    )

    def failing_load(self, item, config):
        del self, config
        raise LoaderRuntimeError(
            f"Playwright loader failed for {item.url}",
            code="INGEST_LOAD_BROWSER_ERROR",
            retryable=True,
            details={
                "phase": "navigate",
                "root_exception_type": "TimeoutError",
                "root_exception_message": "Navigation timeout",
                "url": item.url,
                "wait_until": "networkidle",
                "timeout_ms": 30000,
                "headless": True,
            },
        )

    monkeypatch.setattr(PlaywrightLoaderAdapter, "load", failing_load)

    with pytest.raises(RuntimeError) as exc:
        await handler(Url(value="https://example.com/demo"))
    text = str(exc.value)
    assert (
        "INGEST_LOAD_BROWSER_ERROR Playwright loader failed for https://example.com/demo"
        in text
    )
    diagnostics = json.loads(text.split("diagnostics=", 1)[1])
    assert diagnostics["phase"] == "navigate"
    assert diagnostics["root_exception_type"] == "TimeoutError"


def test_diagnostic_helpers_cover_fallback_paths() -> None:
    assert _format_failure_diagnostics(None) is None
    assert _format_failure_diagnostics({}) is None
    assert _truncate("abc", 2) == "ab"
    assert (
        _sanitize_text("token=abc secret:xyz") == "token=[REDACTED] secret:[REDACTED]"
    )
    assert (
        _sanitize_url("https://example.com/path?token=abc&safe=ok")
        == "https://example.com/path?token=%5BREDACTED%5D&safe=ok"
    )

    # Force payload shrink passes through root/url fallback branches.
    big_meta = {
        "phase": "x",
        "root_exception_type": "RuntimeError",
        "root_exception_message": "x" * 8000,
        "url": "https://example.com/" + ("a" * 4000) + "?token=abc",
        "wait_until": "load",
        "timeout_ms": 1,
        "headless": False,
    }
    diag = _format_failure_diagnostics(big_meta)
    assert diag is not None and len(diag) <= 3072

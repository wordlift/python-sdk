from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from wordlift_sdk.url_source import Url
from wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler import (
    IngestionWebPageScrapeUrlHandler,
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

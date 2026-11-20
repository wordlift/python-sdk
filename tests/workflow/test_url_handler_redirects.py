from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler as _ingestion_mod
from wordlift_sdk.url_source import Url
from wordlift_sdk.workflow.url_handler import (
    FollowRedirects,
    IngestionWebPageScrapeUrlHandler,
    WebPageScrapeUrlHandler,
)
from wordlift_sdk.workflow.url_handler.redirect_policy import resolve_import_target

REQUESTED = Url(
    value="https://example.com/listing/sold-bus",
    iri="https://data.example.com/product/sold-bus-abc",
    import_hash="hash-1",
)
FINAL = "https://example.com/categories/shuttle-buses"


def _ingestion_handler(
    monkeypatch: pytest.MonkeyPatch, final_url: str, follow_redirects: str | None
) -> tuple[IngestionWebPageScrapeUrlHandler, AsyncMock]:
    callback = AsyncMock()
    provider = MagicMock()
    provider.get_value.side_effect = lambda key, default=None: {
        "FOLLOW_REDIRECTS": follow_redirects
    }.get(key, default)
    monkeypatch.setattr(
        _ingestion_mod,
        "run_ingestion",
        lambda settings: SimpleNamespace(
            pages=[
                SimpleNamespace(
                    url=REQUESTED.value,
                    final_url=final_url,
                    status_code=200,
                    html="<html></html>",
                )
            ],
            events=[],
        ),
    )
    handler = IngestionWebPageScrapeUrlHandler(
        context=MagicMock(),
        configuration_provider=provider,
        web_page_scrape_callback=callback,
    )
    return handler, callback


@pytest.mark.asyncio
async def test_ingestion_handler_skips_redirected_page_by_default(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    handler, callback = _ingestion_handler(monkeypatch, FINAL, None)

    with caplog.at_level(logging.WARNING):
        await handler(REQUESTED)

    callback.callback.assert_not_awaited()
    assert f"redirect {REQUESTED.value} -> {FINAL}" in caplog.text


@pytest.mark.asyncio
async def test_ingestion_handler_imports_final_url_without_existing_iri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, callback = _ingestion_handler(monkeypatch, FINAL, "import_final")

    await handler(REQUESTED)

    callback.callback.assert_awaited_once()
    args, kwargs = callback.callback.call_args
    assert args[0].web_page.url == FINAL
    assert kwargs == {"existing_web_page_id": None, "existing_import_hash": None}


@pytest.mark.asyncio
async def test_ingestion_handler_reuses_iri_when_only_query_order_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = Url(value="https://example.com/p?b=2&a=1", iri="iri", import_hash="h")
    handler, callback = _ingestion_handler(
        monkeypatch, "https://example.com/p?a=1&b=2#x", None
    )

    await handler(requested)

    _, kwargs = callback.callback.call_args
    assert kwargs == {"existing_web_page_id": "iri", "existing_import_hash": "h"}


def test_ingestion_handler_rejects_unknown_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="FOLLOW_REDIRECTS"):
        _ingestion_handler(monkeypatch, FINAL, "follow")


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (FollowRedirects.SKIP, None),
        (FollowRedirects.IMPORT_FINAL, (None, None)),
    ],
)
@pytest.mark.asyncio
async def test_web_page_scrape_handler_applies_redirect_policy(
    policy: FollowRedirects, expected: tuple[None, None] | None
) -> None:
    callback = AsyncMock()
    handler = WebPageScrapeUrlHandler(
        context=MagicMock(), web_page_scrape_callback=callback, follow_redirects=policy
    )
    response = SimpleNamespace(web_page=SimpleNamespace(url=FINAL))

    with patch.object(
        WebPageScrapeUrlHandler, "_scrape", AsyncMock(return_value=response)
    ):
        await handler(REQUESTED)

    if expected is None:
        callback.callback.assert_not_awaited()
    else:
        callback.callback.assert_awaited_once_with(
            response, existing_web_page_id=None, existing_import_hash=None
        )


@pytest.mark.parametrize(
    "final_url",
    [None, "", REQUESTED.value, REQUESTED.value + "#section"],
)
def test_same_page_keeps_existing_iri(final_url: str | None) -> None:
    target = resolve_import_target(REQUESTED, final_url, FollowRedirects.SKIP)

    assert target is not None
    assert target.existing_web_page_id == REQUESTED.iri
    assert target.existing_import_hash == REQUESTED.import_hash


def test_parse_accepts_enum_and_text() -> None:
    assert (
        FollowRedirects.parse(FollowRedirects.IMPORT_FINAL)
        is FollowRedirects.IMPORT_FINAL
    )
    assert FollowRedirects.parse(" Import_Final ") is FollowRedirects.IMPORT_FINAL
    assert FollowRedirects.parse("") is FollowRedirects.SKIP

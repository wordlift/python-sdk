from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from wordlift_sdk.url_source import Url, UrlSource
from wordlift_sdk.url_source.new_or_changed_url_source import NewOrChangedUrlSource

IMPORTED = "2026-10-20T00:00:00Z"


class _Urls(UrlSource):
    def __init__(self, *urls: Url) -> None:
        self._urls = urls

    async def urls(self):
        for url in self._urls:
            yield url


def _source(stored: list[dict], overwrite: bool = False) -> NewOrChangedUrlSource:
    return NewOrChangedUrlSource(
        url_provider=_Urls(
            Url(value="https://example.com/no-lastmod"),
            Url(
                value="https://example.com/older",
                date_modified=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
            Url(
                value="https://example.com/newer",
                date_modified=datetime(2026, 10, 25, tzinfo=timezone.utc),
            ),
            Url(value="https://example.com/new"),
        ),
        graphql_client=AsyncMock(run=AsyncMock(return_value=stored)),
        overwrite=overwrite,
    )


def _stored(*urls: str) -> list[dict]:
    return [
        {"url": url, "iri": f"{url}#iri", "import_hash": "h", "date_imported": IMPORTED}
        for url in urls
    ]


async def _values(source: NewOrChangedUrlSource) -> list[str]:
    return [url.value async for url in source.urls()]


@pytest.mark.asyncio
async def test_skips_only_urls_whose_lastmod_predates_the_import() -> None:
    stored = _stored(
        "https://example.com/no-lastmod",
        "https://example.com/older",
        "https://example.com/newer",
    )

    assert await _values(_source(stored)) == [
        "https://example.com/no-lastmod",
        "https://example.com/newer",
        "https://example.com/new",
    ]


@pytest.mark.asyncio
async def test_overwrite_keeps_every_url_with_its_stored_hash() -> None:
    source = _source(_stored("https://example.com/older"), overwrite=True)

    urls = [url async for url in source.urls()]

    assert len(urls) == 4
    (older,) = [url for url in urls if url.value == "https://example.com/older"]
    assert (older.iri, older.import_hash) == ("https://example.com/older#iri", "h")


@pytest.mark.asyncio
async def test_url_with_two_iris_is_yielded_once_with_the_latest_import(
    caplog: pytest.LogCaptureFixture,
) -> None:
    url = "https://example.com/categories/shuttle-buses"
    stored = [
        {
            "url": url,
            "iri": "https://data/b",
            "import_hash": "old",
            "date_imported": "2026-10-01T00:00:00Z",
        },
        {
            "url": url,
            "iri": "https://data/c",
            "import_hash": "new",
            "date_imported": IMPORTED,
        },
        {
            "url": url,
            "iri": "https://data/a",
            "import_hash": "tie",
            "date_imported": IMPORTED,
        },
    ]
    source = NewOrChangedUrlSource(
        url_provider=_Urls(Url(value=url)),
        graphql_client=AsyncMock(run=AsyncMock(return_value=stored)),
        overwrite=True,
    )

    urls = [u async for u in source.urls()]

    assert len(urls) == 1
    assert (urls[0].iri, urls[0].import_hash) == ("https://data/a", "tie")
    assert "1 URL(s) have more than one IRI" in caplog.text

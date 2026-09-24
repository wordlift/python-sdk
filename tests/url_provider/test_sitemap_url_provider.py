import logging
import re

import pandas as pd
import pytest

from wordlift_sdk.url_source import UrlSource, SitemapUrlSource

logger = logging.getLogger(__name__)


@pytest.fixture
def test_wiremock_url(wiremock_url: str) -> str:
    if wiremock_url is None:
        pytest.skip("wiremock/docker is not available in this environment")
    return wiremock_url + "/test_sitemap_url_provider"


@pytest.fixture
def sitemap_url_provider(test_wiremock_url: str) -> UrlSource:
    return SitemapUrlSource(
        sitemap_url=test_wiremock_url + "/MakaleSiteMap.xml",
        pattern=re.compile(r"^https://www.herkesicinguzellik.com/makale/.*$"),
    )


@pytest.mark.asyncio
async def test(sitemap_url_provider: UrlSource) -> None:
    urls = []
    async for url in sitemap_url_provider.urls():
        urls.append(url)

    assert len(urls) == 3565


@pytest.mark.asyncio
async def test_mixed_lastmod_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.url_source.sitemap_url_source.adv.sitemaps.sitemap_to_df",
        lambda *, sitemap_url, request_headers: pd.DataFrame(
            {
                "loc": [
                    "https://example.com/date-only",
                    "https://example.com/full-timestamp",
                ],
                "lastmod": ["2026-09-22", "2024-10-24T12:20:57+00:00"],
            }
        ),
    )
    source = SitemapUrlSource("https://example.com/sitemap.xml")

    urls = [url async for url in source.urls()]

    assert [url.date_modified.isoformat() for url in urls if url.date_modified] == [
        "2026-09-22T00:00:00+00:00",
        "2024-10-24T12:20:57+00:00",
    ]

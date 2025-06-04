import logging
import re

import pytest

from wordlift_sdk.kg.manager.urlprovider import UrlProvider, SitemapUrlProvider

logger = logging.getLogger(__name__)


@pytest.fixture
def test_wiremock_url(wiremock_url: str) -> str:
    return wiremock_url + '/test_sitemap_url_provider'


@pytest.fixture
def sitemap_url_provider(test_wiremock_url: str) -> UrlProvider:
    return SitemapUrlProvider(
        sitemap_url=test_wiremock_url + '/MakaleSiteMap.xml',
        pattern=re.compile(r'^https://www.herkesicinguzellik.com/makale/.*$'),
    )


@pytest.mark.asyncio
async def test(sitemap_url_provider: UrlProvider) -> None:
    urls = []
    async for url in sitemap_url_provider.urls():
        urls.append(url)

    assert len(urls) == 3565

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from wordlift_sdk.configuration import ConfigurationProvider
from wordlift_sdk.container.application_container import ApplicationContainer


def _provider(data: dict[str, object]) -> ConfigurationProvider:
    provider = MagicMock(spec=ConfigurationProvider)
    provider.get_value.side_effect = lambda key, default=None: data.get(key, default)
    return provider


def test_application_container_source_bridge_uses_ingest_source_local() -> None:
    container = ApplicationContainer(
        configuration_provider=_provider(
            {
                "WORDLIFT_KEY": "key",
                "INGEST_SOURCE": "local",
                "INGEST_LOCAL_ITEMS": [
                    {
                        "id": "x",
                        "url": "https://example.com/local",
                        "html": "<html></html>",
                    }
                ],
            }
        )
    )

    async def _collect():
        source = await container.create_url_source()
        return [u async for u in source.urls()]

    urls = asyncio.run(_collect())
    assert len(urls) == 1
    assert urls[0].value == "https://example.com/local"


def test_application_container_source_bridge_priority_urls_over_sitemap() -> None:
    container = ApplicationContainer(
        configuration_provider=_provider(
            {
                "WORDLIFT_KEY": "key",
                "URLS": ["https://example.com/url-list"],
                "SITEMAP_URL": "https://example.com/sitemap.xml",
            }
        )
    )

    async def _collect():
        source = await container.create_url_source()
        return [u async for u in source.urls()]

    urls = asyncio.run(_collect())
    assert [u.value for u in urls] == ["https://example.com/url-list"]

from __future__ import annotations

import asyncio
from dataclasses import asdict
from unittest.mock import MagicMock

import pandas as pd
import pytest

from wordlift_sdk.configuration import ConfigurationProvider
from wordlift_sdk.container.application_container import ApplicationContainer
from wordlift_sdk.ingestion.errors import IngestionConfigError


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
                "INGEST_LOADER": "web_scrape_api",
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


def test_application_container_source_bridge_requires_explicit_ingest_source() -> None:
    container = ApplicationContainer(
        configuration_provider=_provider(
            {
                "WORDLIFT_KEY": "key",
                "URLS": ["https://example.com/url-list"],
                "SITEMAP_URL": "https://example.com/sitemap.xml",
                "INGEST_LOADER": "web_scrape_api",
            }
        )
    )

    async def _collect() -> None:
        source = await container.create_url_source()
        _ = [u async for u in source.urls()]

    with pytest.raises(IngestionConfigError, match="INGEST_SOURCE is required"):
        asyncio.run(_collect())


class _FakeGraphQlClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def run(self, operation: str, variables: dict[str, object]):
        self.calls.append((operation, variables))
        return []


def test_graph_sync_sitemap_filtering_uses_url_regex_before_graphql_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.adv.sitemaps.sitemap_to_df",
        lambda *, sitemap_url, request_headers: pd.DataFrame(
            {
                "loc": [
                    "https://example.com/auto/deals",
                    "https://example.com/credit-cards/best/citi",
                ]
            }
        ),
    )

    container = ApplicationContainer(
        configuration_provider=_provider(
            {
                "WORDLIFT_KEY": "key",
                "INGEST_SOURCE": "sitemap",
                "INGEST_LOADER": "web_scrape_api",
                "SITEMAP_URL": "https://example.com/sitemap.xml",
                "URL_REGEX": r"^https://example.com/auto/.*",
            }
        )
    )
    fake_graphql = _FakeGraphQlClient()
    container._graphql_client = fake_graphql

    async def _collect() -> list[dict[str, object]]:
        source = await container.create_new_or_changed_source()
        return [asdict(url) async for url in source.urls()]

    rows = asyncio.run(_collect())
    assert fake_graphql.calls == [
        (
            "entities_url_iri_with_source_equal_to_web_page_import",
            {"urls": ["https://example.com/auto/deals"]},
        )
    ]
    assert [row["value"] for row in rows] == ["https://example.com/auto/deals"]


def test_graph_sync_sitemap_filtering_supports_sitemap_url_pattern_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.adv.sitemaps.sitemap_to_df",
        lambda *, sitemap_url, request_headers: pd.DataFrame(
            {
                "loc": [
                    "https://example.com/auto/rates",
                    "https://example.com/home-insurance",
                ]
            }
        ),
    )

    container = ApplicationContainer(
        configuration_provider=_provider(
            {
                "WORDLIFT_KEY": "key",
                "INGEST_SOURCE": "sitemap",
                "INGEST_LOADER": "web_scrape_api",
                "SITEMAP_URL": "https://example.com/sitemap.xml",
                "SITEMAP_URL_PATTERN": r"/auto/.*",
            }
        )
    )
    fake_graphql = _FakeGraphQlClient()
    container._graphql_client = fake_graphql

    async def _collect_values() -> list[str]:
        source = await container.create_new_or_changed_source()
        return [url.value async for url in source.urls()]

    values = asyncio.run(_collect_values())
    assert fake_graphql.calls == [
        (
            "entities_url_iri_with_source_equal_to_web_page_import",
            {"urls": ["https://example.com/auto/rates"]},
        )
    ]
    assert values == ["https://example.com/auto/rates"]


def test_graph_sync_sitemap_without_filter_keeps_all_urls_for_graphql_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.adv.sitemaps.sitemap_to_df",
        lambda *, sitemap_url, request_headers: pd.DataFrame(
            {
                "loc": [
                    "https://example.com/auto/rates",
                    "https://example.com/credit-cards",
                ]
            }
        ),
    )

    container = ApplicationContainer(
        configuration_provider=_provider(
            {
                "WORDLIFT_KEY": "key",
                "INGEST_SOURCE": "sitemap",
                "INGEST_LOADER": "web_scrape_api",
                "SITEMAP_URL": "https://example.com/sitemap.xml",
            }
        )
    )
    fake_graphql = _FakeGraphQlClient()
    container._graphql_client = fake_graphql

    async def _collect_values() -> list[str]:
        source = await container.create_new_or_changed_source()
        return [url.value async for url in source.urls()]

    values = asyncio.run(_collect_values())
    assert fake_graphql.calls == [
        (
            "entities_url_iri_with_source_equal_to_web_page_import",
            {
                "urls": [
                    "https://example.com/auto/rates",
                    "https://example.com/credit-cards",
                ]
            },
        )
    ]
    assert values == [
        "https://example.com/auto/rates",
        "https://example.com/credit-cards",
    ]

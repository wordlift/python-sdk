from unittest.mock import AsyncMock, MagicMock

import pytest

from wordlift_sdk.configuration import ConfigurationProvider
from wordlift_sdk.kg_build.container import KgBuildApplicationContainer
from wordlift_sdk.workflow.url_handler.default_url_handler import DefaultUrlHandler
from wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler import (
    IngestionWebPageScrapeUrlHandler,
)
from wordlift_sdk.workflow.url_handler.search_console_url_handler import (
    SearchConsoleUrlHandler,
)


def _make_provider(overrides: dict[str, object] | None = None) -> ConfigurationProvider:
    config = {
        "API_URL": "https://api.wordlift.io",
        "WORDLIFT_KEY": "test-key",
    }
    if overrides:
        config.update(overrides)

    provider = MagicMock(spec=ConfigurationProvider)
    provider.get_value.side_effect = lambda key, default=None: config.get(key, default)
    return provider


@pytest.mark.asyncio
async def test_create_multi_url_handler_includes_search_console_by_default():
    container = KgBuildApplicationContainer(configuration_provider=_make_provider())
    web_handler = MagicMock()
    gsc_handler = MagicMock(spec=SearchConsoleUrlHandler)
    container.create_web_page_scrape_url_handler = AsyncMock(return_value=web_handler)
    container.create_search_console_url_handler = AsyncMock(return_value=gsc_handler)

    handler = await container.create_multi_url_handler()

    assert isinstance(handler, DefaultUrlHandler)
    assert handler._url_handler_list == [web_handler, gsc_handler]


@pytest.mark.asyncio
async def test_create_multi_url_handler_disables_search_console_when_configured():
    container = KgBuildApplicationContainer(
        configuration_provider=_make_provider({"GOOGLE_SEARCH_CONSOLE": False})
    )
    web_handler = MagicMock()
    container.create_web_page_scrape_url_handler = AsyncMock(return_value=web_handler)
    container.create_search_console_url_handler = AsyncMock()

    handler = await container.create_multi_url_handler()

    assert isinstance(handler, DefaultUrlHandler)
    assert handler._url_handler_list == [web_handler]
    container.create_search_console_url_handler.assert_not_called()


@pytest.mark.asyncio
async def test_create_web_page_scrape_url_handler_passes_protocol_callback():
    protocol = MagicMock()
    container = KgBuildApplicationContainer(configuration_provider=_make_provider())
    container.set_protocol(protocol)
    container.get_context = AsyncMock(return_value=MagicMock())

    handler = await container.create_web_page_scrape_url_handler()

    assert isinstance(handler, IngestionWebPageScrapeUrlHandler)
    assert handler._web_page_scrape_callback is protocol

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import wordlift_sdk.workflow.url_handler.web_page_import_url_handler as handler_module
from wordlift_sdk.container.application_container import ApplicationContainer
from wordlift_sdk.configuration import ConfigurationProvider
from wordlift_sdk.url_source import Url
from wordlift_client import WebPageImportFetchOptions, WebPageImportRequest


@pytest.mark.asyncio
async def test_web_page_import_url_handler_passes_fetch_options():
    # Mock context and its attributes
    mock_context = MagicMock()
    mock_context.client_configuration = MagicMock()

    fetch_options = WebPageImportFetchOptions(
        mode="premium_scraper", render_js=True, wait_for=".content"
    )

    handler = handler_module.WebPageImportUrlHandler(
        context=mock_context,
        embedding_properties=["prop1"],
        web_page_types=["Type1"],
        fetch_options=fetch_options,
    )

    url = Url(value="https://example.com", iri="https://example.com/iri")

    # Mock ApiClient and WebPagesImportsApi
    with patch.object(handler_module, "ApiClient") as mock_api_client_class:
        mock_api_client = AsyncMock()
        mock_api_client_class.return_value.__aenter__.return_value = mock_api_client

        with patch.object(
            handler_module, "WebPagesImportsApi"
        ) as mock_api_instance_class:
            mock_api_instance = AsyncMock()
            mock_api_instance_class.return_value = mock_api_instance

            # Mock the callback
            handler._web_page_import_callback = AsyncMock()

            await handler(url)

            # Verify WebPageImportRequest was created with correct fetch_options
            mock_api_instance.create_web_page_imports.assert_called_once()
            args, kwargs = mock_api_instance.create_web_page_imports.call_args
            request = kwargs["web_page_import_request"]

            assert isinstance(request, WebPageImportRequest)
            assert request.url == "https://example.com"
            assert request.fetch_options == fetch_options
            assert request.fetch_options.mode == "premium_scraper"
            assert request.fetch_options.render_js is True
            assert request.fetch_options.wait_for == ".content"


@pytest.mark.asyncio
async def test_application_container_initializes_fetch_options():
    config = {
        "WORDLIFT_KEY": "test-key",
        "WEB_PAGE_IMPORT_MODE": "proxy",
        "WEB_PAGE_IMPORT_RENDER_JS": True,
        "WEB_PAGE_IMPORT_WAIT_FOR": "#main",
        "WEB_PAGE_IMPORT_TIMEOUT": 5000,
    }

    mock_provider = MagicMock(spec=ConfigurationProvider)
    mock_provider.get_value.side_effect = lambda key, default=None: config.get(
        key, default
    )

    with patch(
        "wordlift_sdk.container.application_container.ConfigurationProvider.create",
        return_value=mock_provider,
    ):
        container = ApplicationContainer(configuration_provider=mock_provider)

        # Mock get_context to avoid complex setup
        container.get_context = AsyncMock()

        handler = await container.create_web_page_import_url_handler()

        assert isinstance(handler, handler_module.WebPageImportUrlHandler)
        assert handler._fetch_options is not None
        assert handler._fetch_options.mode == "proxy"
        assert handler._fetch_options.render_js is True
        assert handler._fetch_options.wait_for == "#main"
        assert handler._fetch_options.timeout == 5000

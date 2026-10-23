from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wordlift_client import WebPageImportFetchOptions, WebPageScrapeRequest

from wordlift_sdk.url_source import Url
from wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler import (
    WebPageScrapeUrlHandler,
)


@pytest.mark.asyncio
async def test_web_page_scrape_handler_passes_fetch_options_and_existing_id():
    mock_context = MagicMock()
    mock_context.client_configuration = MagicMock()

    fetch_options = WebPageImportFetchOptions(mode="premium_scraper", render_js=True)
    callback = AsyncMock()
    handler = WebPageScrapeUrlHandler(
        context=mock_context,
        web_page_scrape_callback=callback,
        fetch_options=fetch_options,
    )
    url = Url(
        value="https://example.com/page",
        iri="https://example.com/entity/1",
        import_hash="abc123",
    )

    with patch(
        "wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler.ApiClient"
    ) as mock_api_client_class:
        mock_api_client = AsyncMock()
        mock_api_client_class.return_value.__aenter__.return_value = mock_api_client

        with patch(
            "wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler.WebPageScrapeApi"
        ) as mock_api_instance_class:
            mock_api_instance = AsyncMock()
            mock_api_instance_class.return_value = mock_api_instance
            mock_response = MagicMock()
            mock_api_instance.create_web_page_scrape.return_value = mock_response

            await handler(url)

            mock_api_instance.create_web_page_scrape.assert_called_once()
            _, kwargs = mock_api_instance.create_web_page_scrape.call_args
            request = kwargs["web_page_scrape_request"]
            assert isinstance(request, WebPageScrapeRequest)
            assert request.url == "https://example.com/page"
            assert request.fetch_options == fetch_options

            callback.callback.assert_awaited_once_with(
                mock_response,
                existing_web_page_id="https://example.com/entity/1",
                existing_import_hash="abc123",
            )


@pytest.mark.asyncio
async def test_web_page_scrape_handler_does_not_retry_failing_callback():
    import wordlift_client

    mock_context = MagicMock()
    callback = AsyncMock()
    callback.callback.side_effect = wordlift_client.exceptions.ServiceException(
        status=500, reason="Internal Server Error"
    )
    handler = WebPageScrapeUrlHandler(
        context=mock_context, web_page_scrape_callback=callback
    )

    with patch(
        "wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler.ApiClient"
    ) as mock_api_client_class:
        mock_api_client_class.return_value.__aenter__.return_value = AsyncMock()
        with patch(
            "wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler.WebPageScrapeApi"
        ) as mock_api_instance_class:
            mock_api_instance = AsyncMock()
            mock_api_instance_class.return_value = mock_api_instance

            with pytest.raises(wordlift_client.exceptions.ServiceException):
                await handler(Url(value="https://example.com/page"))

            mock_api_instance.create_web_page_scrape.assert_awaited_once()
            callback.callback.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_page_scrape_handler_retries_transient_request_error(no_retry_wait):
    import wordlift_client

    no_retry_wait(WebPageScrapeUrlHandler._scrape)
    callback = AsyncMock()
    handler = WebPageScrapeUrlHandler(
        context=MagicMock(), web_page_scrape_callback=callback
    )
    response = MagicMock()

    with patch(
        "wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler.ApiClient"
    ) as mock_api_client_class:
        mock_api_client_class.return_value.__aenter__.return_value = AsyncMock()
        with patch(
            "wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler.WebPageScrapeApi"
        ) as mock_api_instance_class:
            mock_api_instance = AsyncMock()
            mock_api_instance_class.return_value = mock_api_instance
            mock_api_instance.create_web_page_scrape.side_effect = [
                wordlift_client.exceptions.ServiceException(status=503),
                response,
            ]

            await handler(Url(value="https://example.com/page"))

            assert mock_api_instance.create_web_page_scrape.await_count == 2
            callback.callback.assert_awaited_once_with(
                response, existing_web_page_id=None, existing_import_hash=None
            )

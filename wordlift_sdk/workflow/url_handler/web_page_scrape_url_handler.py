import asyncio
import logging

import aiohttp
import gql.transport.exceptions
import pydantic_core
import wordlift_client
from tenacity import (
    after_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from wordlift_client import (
    ApiClient,
    WebPageImportFetchOptions,
    WebPageScrapeApi,
    WebPageScrapeRequest,
)

from ...protocol import Context, WebPageImportProtocolInterface
from ...url_source import Url
from .url_handler import UrlHandler

logger = logging.getLogger(__name__)


class WebPageScrapeUrlHandler(UrlHandler):
    _context: Context
    _fetch_options: WebPageImportFetchOptions | None
    _web_page_scrape_callback: WebPageImportProtocolInterface

    def __init__(
        self,
        context: Context,
        web_page_scrape_callback: WebPageImportProtocolInterface,
        fetch_options: WebPageImportFetchOptions | None = None,
    ):
        self._context = context
        self._web_page_scrape_callback = web_page_scrape_callback
        self._fetch_options = fetch_options

    @retry(
        retry=retry_if_exception_type(
            asyncio.TimeoutError
            | aiohttp.client_exceptions.ServerDisconnectedError
            | aiohttp.client_exceptions.ClientConnectorError
            | aiohttp.client_exceptions.ClientPayloadError
            | aiohttp.client_exceptions.ClientConnectorDNSError
            | pydantic_core.ValidationError
            | wordlift_client.exceptions.ServiceException
            | gql.transport.exceptions.TransportServerError
            | wordlift_client.exceptions.BadRequestException
            | aiohttp.client_exceptions.ClientOSError
        ),
        wait=wait_fixed(2),
        after=after_log(logger, logging.WARNING),
        stop=stop_after_attempt(5),
    )
    async def __call__(self, url: Url) -> None:
        async with ApiClient(self._context.client_configuration) as client:
            api_instance = WebPageScrapeApi(client)

            request = WebPageScrapeRequest(
                url=url.value,
                fetch_options=self._fetch_options,
            )

            try:
                response = await api_instance.create_web_page_scrape(
                    web_page_scrape_request=request, _request_timeout=120.0
                )
                await self._web_page_scrape_callback.callback(
                    response,
                    existing_web_page_id=url.iri,
                )
            except Exception as e:
                logger.error("Error scraping Web Page %s", url.value, exc_info=e)
                raise e

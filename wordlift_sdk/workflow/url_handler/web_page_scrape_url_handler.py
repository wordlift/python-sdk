import logging

from wordlift_client import (
    ApiClient,
    WebPageImportFetchOptions,
    WebPageScrapeApi,
    WebPageScrapeRequest,
    WebPageScrapeResponse,
)

from ...protocol import Context, WebPageImportProtocolInterface
from ...protocol.retry_policy import retry_transient
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

    @retry_transient(logger)
    async def _scrape(self, url: Url) -> WebPageScrapeResponse:
        async with ApiClient(self._context.client_configuration) as client:
            api_instance = WebPageScrapeApi(client)

            request = WebPageScrapeRequest(
                url=url.value,
                fetch_options=self._fetch_options,
            )

            return await api_instance.create_web_page_scrape(
                web_page_scrape_request=request, _request_timeout=120.0
            )

    async def __call__(self, url: Url) -> None:
        # Only the scrape request is retried here. The callback writes the
        # graph through queues that retry on their own, so retrying it again
        # would multiply the writes.
        response = await self._scrape(url)
        await self._web_page_scrape_callback.callback(
            response,
            existing_web_page_id=url.iri,
            existing_import_hash=url.import_hash,
        )

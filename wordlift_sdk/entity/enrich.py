import logging
from typing import Callable, Awaitable, Coroutine

from aiohttp import ClientSession
from pandas import Series
from tenacity import retry, stop_after_attempt, wait_fixed
from wordlift_client import EntityPatchRequest, Configuration, WebPagesApi
import wordlift_client

from .patch import patch
from ..wordlift.sitemap_import.protocol.parse_html_protocol_interface import ParseHtmlInput

logger = logging.getLogger(__name__)

ParseHtmlCallback = Callable[[ParseHtmlInput], Awaitable[list[EntityPatchRequest]]]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def enrich(configuration: Configuration, callback: ParseHtmlCallback) -> Callable[
    [Series], Coroutine[None, None, None]]:
    @retry(
        stop=stop_after_attempt(5),  # Retry up to 5 times
        wait=wait_fixed(2)  # Wait 2 seconds between retries
    )
    async def process(row: Series) -> None:
        entity_url = row['url']
        entity_id = row['iri']

        async with wordlift_client.ApiClient(configuration) as api_client:
            try:
                api_instance = WebPagesApi(api_client=api_client)
                web_page = await api_instance.get_web_page(entity_url)
                html = web_page.html
                parse_html_input = ParseHtmlInput(
                    entity_id=entity_id,
                    entity_url=entity_url,
                    html=html,
                    row=row
                )
                payloads = await callback(parse_html_input)
                await patch(configuration, entity_id, payloads)
            except Exception as e:
                logger.error("Error %s occurred while processing entity %s with url %s" % (e, entity_id, entity_url))

    return process

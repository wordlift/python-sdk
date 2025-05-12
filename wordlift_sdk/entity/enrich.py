from typing import Callable, Awaitable, Coroutine

from aiohttp import ClientSession
from pandas import Series
from tenacity import retry, stop_after_attempt, wait_fixed
from wordlift_client import EntityPatchRequest, Configuration

from .patch import patch
from ..wordlift.sitemap_import.protocol.parse_html_protocol_interface import ParseHtmlInput

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


def enrich(configuration: Configuration, callback: ParseHtmlCallback) -> Callable[[Series], Coroutine[None, None, None]]:
    async def fetch(session: ClientSession, url: str) -> str:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()  # Optional: raise exception on HTTP errors
            return await response.text()

    @retry(
        stop=stop_after_attempt(5),  # Retry up to 5 times
        wait=wait_fixed(2)  # Wait 2 seconds between retries
    )
    async def process(row: Series) -> None:
        async with ClientSession() as session:
            entity_url = row['url']
            entity_id = row['iri']
            html = await fetch(session, entity_url)
            enrich_input = ParseHtmlInput(
                entity_id=entity_id,
                entity_url=entity_url,
                html=html,
                row=row
            )
            payloads = await callback(enrich_input)
            await patch(configuration, entity_id, payloads)

    return process

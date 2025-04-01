from typing import Callable, Awaitable, Coroutine

from aiohttp import ClientSession
from pandas import Series
from tenacity import retry, stop_after_attempt, wait_fixed
from wordlift_client import EntityPatchRequest, Configuration

from .patch import patch


@retry(
    stop=stop_after_attempt(5),  # Retry up to 5 times
    wait=wait_fixed(2)  # Wait 2 seconds between retries
)
def enrich(configuration: Configuration, callback: Callable[[str, str], Awaitable[list[EntityPatchRequest]]]) -> \
        Callable[
            [Series], Coroutine[None, None, None]]:
    async def fetch(session: ClientSession, url: str) -> str:
        async with session.get(url) as response:
            return await response.text()

    async def process(row: Series) -> None:
        async with ClientSession() as session:
            entity_url = row['url']
            entity_id = row['iri']
            html = await fetch(session, entity_url)
            payloads = await callback(entity_id, html)
            await patch(configuration, entity_id, payloads)

    return process

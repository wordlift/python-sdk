from typing import Callable, Awaitable, Optional

import wordlift_client
from pandas import Series
from tenacity import retry, stop_after_attempt, wait_fixed
from twisted.mail.scripts.mailmail import Configuration
from wordlift_client import AnalysesResponse, EntityGapsApi, EntityGapRequest


async def entity_gaps_callback_factory(configuration: Configuration, query_location_name: str) -> Callable[
    [Series], Awaitable[Optional[AnalysesResponse]]]:
    @retry(
        stop=stop_after_attempt(10),
        wait=wait_fixed(2)
    )
    async def entity_gaps_callback(row: Series) -> Optional[AnalysesResponse]:
        url = row['url']
        query = row['top_query_name']
        if query is None:
            return None

        async with wordlift_client.ApiClient(configuration) as api_client:
            api = EntityGapsApi(api_client)
            return await api.create_entity_gap(
                EntityGapRequest(
                    url=url,
                    query=query,
                    query_location_name=query_location_name
                )
            )

    return entity_gaps_callback

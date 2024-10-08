import logging
from typing import List, AsyncGenerator

import pandas as pd
from gql import Client, gql
from pandas.core.interchange.dataframe_protocol import DataFrame
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed, RetryError

from wordlift_sdk.kg import Entity

logger = logging.getLogger(__name__)


class EntityStore:
    _gql_client: Client

    def __init__(self, gql_client: Client):
        self._gql_client = gql_client

    async def url_id(self, url_list: List[str] = None) -> AsyncGenerator[Entity, None]:
        # the query.
        query = gql(
            """
            query entities_url_id($urls: [String]!) {
                entities(query: { urlConstraint: { in: $urls } } ) {
                    url: string(name:"schema:url")
                    id: iri
                }
            }
            """
        )

        # the variables.
        values = {"urls": url_list}

        try:
            async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_fixed(2)):
                with attempt:
                    logger.debug(
                        'Loading data from GraphQL with attempt %d', attempt.retry_state.attempt_number)
                    response = await self._gql_client.execute_async(query, variable_values=values)
                    for item in response['entities']:
                        yield Entity(item)
        except RetryError as e:
            logger.error('Error loading data from GraphQL', exc_info=True)

    async def url_id_as_dataframe(self, url_list: List[str] = None) -> DataFrame:
        """
        Get the Entity URL ID maps as a Pandas dataframe.

        :param url_list:
        :return:
        """
        return pd.DataFrame.from_records(
            data=[(entity.url, entity.id) async for entity in self.url_id(url_list)],
            columns=("url", "id"))

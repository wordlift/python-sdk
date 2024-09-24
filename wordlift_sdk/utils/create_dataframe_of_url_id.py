from typing import List

import pandas as pd

from wordlift_sdk.graphql import GraphQLClientFactory
from wordlift_sdk.kg import EntityStoreFactory


async def create_dataframe_of_url_id(key: str, url_list: List[str]) -> pd.DataFrame:
    graphql_client_factory = GraphQLClientFactory(key)
    graphql_client = graphql_client_factory.create()
    entity_store_factory = EntityStoreFactory(graphql_client)
    entity_store = entity_store_factory.create()
    return await entity_store.url_id_as_dataframe(url_list)

from typing import List

import pandas as pd

from ..graphql.client.factory import GraphQlClientFactory
from wordlift_sdk.kg import EntityStoreFactory


async def create_dataframe_of_url_iri(key: str, url_list: List[str]) -> pd.DataFrame:
    graphql_client_factory = GraphQlClientFactory(key)
    graphql_client = graphql_client_factory.create_gql_client()
    entity_store_factory = EntityStoreFactory(graphql_client)
    entity_store = entity_store_factory.create()
    return await entity_store.url_iri_as_dataframe(url_list)

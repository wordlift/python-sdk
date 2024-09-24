import asyncio
from typing import List

import pytest
from gql import Client

from wordlift_sdk.graphql import GraphQLClientFactory
from wordlift_sdk.kg import EntityStore, EntityStoreFactory

import pandas as pd


@pytest.fixture(scope="session")
def graphql_client_factory() -> GraphQLClientFactory:
    return GraphQLClientFactory("2wOlNzVh4zcgsblumPyj331AeJYI8rEhJK7ruaXyj3lXVtnQaxNo5Qr2iJsMxkKV")


@pytest.fixture(scope="session")
def graphql_client(graphql_client_factory: GraphQLClientFactory) -> Client:
    return graphql_client_factory.create()


@pytest.fixture(scope="session")
def entity_store_factory(graphql_client: Client) -> EntityStoreFactory:
    return EntityStoreFactory(graphql_client)


@pytest.fixture(scope="session")
def entity_store(entity_store_factory: EntityStoreFactory) -> EntityStore:
    return entity_store_factory.create()


@pytest.fixture(scope="session")
def url_list() -> List[str]:
    with open("url_list.txt", "r") as f:
        return f.read().splitlines()


@pytest.mark.asyncio()
async def test_generator(entity_store: EntityStore, url_list: List[str]) -> None:
    count = 0
    async for _ in entity_store.url_id(url_list):
        count += 1

    assert 4741 == count


@pytest.mark.asyncio()
async def test_dataframe(entity_store: EntityStore, url_list: List[str]) -> None:
    df = pd.DataFrame.from_records(data=[(entity.url, entity.id) async for entity in entity_store.url_id(url_list)],
                                   columns=("url", "id"))
    # async for entity in entity_store.uri_to_id(url_list):
    #     df.append(entity)
    assert 4741 == len(df)

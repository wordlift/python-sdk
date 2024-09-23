from gql import Client

from wordlift_sdk.kg import EntityStore


class EntityStoreFactory:
    _gql_client: Client

    def __init__(self, gql_client: Client):
        self._gql_client = gql_client

    def create(self):
        return EntityStore(self._gql_client)

from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport

from .client import GraphQlClient


class GraphQlClientFactory:
    _api_url: str
    _key: str

    def __init__(self, key: str, api_url: str = "https://api.wordlift.io/graphql"):
        self._api_url = api_url
        self._key = key

    def create(self) -> GraphQlClient:
        client = self.create_gql_client()
        return GraphQlClient(client)

    def create_gql_client(self) -> Client:
        # Select your transport with a defined url endpoint
        transport = AIOHTTPTransport(
            url=self._api_url,
            ssl=True,
            headers={
                'Authorization': f'Key {self._key}',
                'X-include-Private': 'true'
            },
        )

        # Create a GraphQL client using the defined transport
        return Client(transport=transport, fetch_schema_from_transport=False, execute_timeout=120)

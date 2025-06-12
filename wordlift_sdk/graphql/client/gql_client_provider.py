from gql import Client
from gql.transport.aiohttp import AIOHTTPTransport


class GqlClientProvider:
    _api_url: str
    _key: str

    def __init__(self, key: str, api_url: str = "https://api.wordlift.io/graphql"):
        self._api_url = api_url
        self._key = key

    def _create_transport(self) -> AIOHTTPTransport:
        # Select your transport with a defined url endpoint
        return AIOHTTPTransport(
            url=self._api_url,
            ssl=True,
            headers={"Authorization": f"Key {self._key}", "X-include-Private": "true"},
        )

    def create(self) -> Client:
        return Client(
            transport=self._create_transport(),
            fetch_schema_from_transport=False,
            execute_timeout=120,
        )

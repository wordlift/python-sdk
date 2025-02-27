import wordlift_client


class ClientConfigurationFactory:
    _api_url: str
    _key: str

    def __init__(self, key: str, api_url: str = "https://api.wordlift.io"):
        self._api_url = api_url
        self._key = key

    def create(self):
        configuration = wordlift_client.Configuration(
            host=self._api_url,
        )

        # The client must configure the authentication and authorization parameters
        # in accordance with the API server security policy.
        # Examples for each auth method are provided below, use the example that
        # satisfies your auth use case.

        # Configure API key authorization: ApiKey
        configuration.api_key['ApiKey'] = self._key
        configuration.api_key_prefix['ApiKey'] = 'Key'

        return configuration

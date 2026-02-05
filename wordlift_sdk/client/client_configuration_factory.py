import wordlift_client

from wordlift_sdk.utils.ssl_ca_bundle import resolve_ssl_ca_cert


class ClientConfigurationFactory:
    _api_url: str
    _key: str
    _ssl_ca_cert: str | None

    def __init__(
        self,
        key: str,
        api_url: str = "https://api.wordlift.io",
        ssl_ca_cert: str | None = None,
    ):
        self._api_url = api_url
        self._key = key
        self._ssl_ca_cert = ssl_ca_cert

    def create(self):
        configuration = wordlift_client.Configuration(
            host=self._api_url,
        )

        # The client must configure the authentication and authorization parameters
        # in accordance with the API server security policy.
        # Examples for each auth method are provided below, use the example that
        # satisfies your auth use case.

        # Configure API key authorization: ApiKey
        configuration.api_key["ApiKey"] = self._key
        configuration.api_key_prefix["ApiKey"] = "Key"

        configuration.verify_ssl = True

        ssl_ca_cert = resolve_ssl_ca_cert(self._ssl_ca_cert)
        if ssl_ca_cert:
            configuration.ssl_ca_cert = ssl_ca_cert

        return configuration

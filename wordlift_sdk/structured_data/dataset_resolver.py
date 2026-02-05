"""Dataset resolution helpers."""

from __future__ import annotations

from wordlift_client import ApiClient

from wordlift_sdk.structured_data.constants import DEFAULT_BASE_URL

from .engine import (
    _build_agent_client,
    _build_client,
    get_dataset_uri,
    get_dataset_uri_async,
)


class DatasetResolver:
    """Resolves dataset URIs and builds API clients."""

    def build_client(
        self, api_key: str, base_url: str, ssl_ca_cert: str | None = None
    ) -> ApiClient:
        return _build_client(api_key, base_url, ssl_ca_cert=ssl_ca_cert)

    def build_agent_client(
        self, api_key: str, ssl_ca_cert: str | None = None
    ) -> ApiClient:
        return _build_agent_client(api_key, ssl_ca_cert=ssl_ca_cert)

    async def get_dataset_uri_async(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        ssl_ca_cert: str | None = None,
    ) -> str:
        return await get_dataset_uri_async(api_key, base_url, ssl_ca_cert=ssl_ca_cert)

    def get_dataset_uri(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        ssl_ca_cert: str | None = None,
    ) -> str:
        return get_dataset_uri(api_key, base_url, ssl_ca_cert=ssl_ca_cert)

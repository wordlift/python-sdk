from __future__ import annotations

import pytest
from tenacity import RetryError

import wordlift_sdk.kg.entity_store as entity_store_module
from wordlift_sdk.kg.entity_store import EntityStore


class _GqlClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def execute_async(self, query, variable_values=None):
        self.calls.append(variable_values)
        return self.response


@pytest.mark.asyncio
async def test_url_id_and_url_iri_generators():
    client = _GqlClient(
        {
            "entities": [
                {"url": "https://example.org/a", "iri": "urn:a"},
                {"url": "https://example.org/b", "iri": "urn:b"},
            ]
        }
    )
    store = EntityStore(client)

    url_ids = [entity async for entity in store.url_id(["https://example.org/a"])]
    url_iris = [entity async for entity in store.url_iri(["https://example.org/b"])]

    assert len(url_ids) == 2
    assert url_ids[0].url == "https://example.org/a"
    assert url_ids[0].iri == "urn:a"
    assert len(url_iris) == 2
    assert client.calls[0] == {"urls": ["https://example.org/a"]}
    assert client.calls[1] == {"urls": ["https://example.org/b"]}


@pytest.mark.asyncio
async def test_dataframe_helpers():
    client = _GqlClient(
        {"entities": [{"url": "https://example.org/a", "iri": "urn:a"}]}
    )
    store = EntityStore(client)

    df_id = await store.url_id_as_dataframe(["https://example.org/a"])
    df_iri = await store.url_iri_as_dataframe(["https://example.org/a"])

    assert list(df_id.columns) == ["url", "id"]
    assert df_id.iloc[0].to_dict() == {"url": "https://example.org/a", "id": "urn:a"}
    assert list(df_iri.columns) == ["url", "iri"]
    assert df_iri.iloc[0].to_dict() == {"url": "https://example.org/a", "iri": "urn:a"}


@pytest.mark.asyncio
async def test_retry_error_is_handled(monkeypatch: pytest.MonkeyPatch):
    class _Retrying:
        def __init__(self, *args, **kwargs):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RetryError(None)

    monkeypatch.setattr(entity_store_module, "AsyncRetrying", _Retrying)
    store = EntityStore(_GqlClient({"entities": []}))

    result_id = [entity async for entity in store.url_id(["https://example.org/a"])]
    result_iri = [entity async for entity in store.url_iri(["https://example.org/a"])]

    assert result_id == []
    assert result_iri == []

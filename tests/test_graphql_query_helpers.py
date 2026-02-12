import importlib
import sys
import types

import pandas as pd
import pytest

from wordlift_sdk.graphql.utils.query.entity_top_query import EntityTopQuery
from wordlift_sdk.graphql.utils.query.entity_with_top_query import (
    entity_with_top_query_factory,
)

graphql_query = importlib.import_module("wordlift_sdk.graphql.query")


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.received = None

    async def execute(self, gql_query, variable_values=None):
        self.received = (gql_query, variable_values)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self._session = _FakeSession(response)

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeFactory:
    def __init__(self, key, response):
        self.key = key
        self.response = response

    def create_gql_client(self):
        return _FakeClient(self.response)


@pytest.mark.asyncio
async def test_query_builds_dataframe_and_passes_variables(monkeypatch):
    response = {"entities": [{"iri": "urn:1", "url": "https://example.org"}]}

    monkeypatch.setattr(
        graphql_query, "GraphQlClientFactory", lambda key: _FakeFactory(key, response)
    )

    fake_gql_module = types.SimpleNamespace(gql=lambda value: f"GQL::{value}")
    monkeypatch.setitem(sys.modules, "gql", fake_gql_module)

    df = await graphql_query.query(
        key="k",
        query_string="query { entities { iri url } }",
        root_element="entities",
        columns=["iri", "url"],
        variable_values={"url": "https://example.org"},
    )

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["iri", "url"]
    assert df.iloc[0].to_dict()["iri"] == "urn:1"


@pytest.mark.asyncio
async def test_entity_with_top_query_factory_returns_entity(monkeypatch):
    module = importlib.import_module(
        "wordlift_sdk.graphql.utils.query.entity_with_top_query"
    )
    response = {
        "entities": [
            {
                "iri": "urn:entity",
                "url": "https://example.org/p",
                "name": "Name",
                "headline": "Headline",
                "title": "Title",
                "top_query": [
                    {
                        "iri": "urn:q",
                        "name": "query",
                        "impressions": 10,
                        "clicks": 1,
                        "date_created": "2025-01-01",
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(
        module, "GraphQlClientFactory", lambda key: _FakeFactory(key, response)
    )
    monkeypatch.setitem(
        sys.modules, "gql", types.SimpleNamespace(gql=lambda value: value)
    )

    fn = await entity_with_top_query_factory("k")
    result = await fn("https://example.org/p")

    assert isinstance(result, EntityTopQuery)
    assert result.iri == "urn:entity"
    assert result.top_query_name == "query"


@pytest.mark.asyncio
async def test_entity_with_top_query_factory_returns_none_when_empty(monkeypatch):
    module = importlib.import_module(
        "wordlift_sdk.graphql.utils.query.entity_with_top_query"
    )
    monkeypatch.setattr(
        module, "GraphQlClientFactory", lambda key: _FakeFactory(key, {"entities": []})
    )
    monkeypatch.setitem(
        sys.modules, "gql", types.SimpleNamespace(gql=lambda value: value)
    )

    fn = await entity_with_top_query_factory("k")
    result = await fn("https://example.org/missing")

    assert result is None


def test_entity_top_query_from_graphql_response_and_dataframe():
    entity = EntityTopQuery.from_graphql_response(
        {
            "iri": "urn:entity",
            "url": "https://example.org/p",
            "name": "Name",
            "headline": "Headline",
            "title": "Title",
            "top_query": [
                {
                    "iri": "urn:q",
                    "name": "query",
                    "impressions": 10,
                    "clicks": 1,
                    "date_created": "2025-01-01",
                }
            ],
        }
    )

    df = entity.to_dataframe()
    assert df.loc[0, "calc_name"] == "Name"
    assert str(df.loc[0, "top_query_date_created"].date()) == "2025-01-01"


def test_entity_top_query_from_graphql_response_without_top_query():
    entity = EntityTopQuery.from_graphql_response(
        {
            "iri": "urn:entity",
            "url": "https://example.org/p",
            "name": "",
            "headline": "Headline",
            "title": "Title",
            "top_query": [],
        }
    )
    assert entity.top_query_iri is None

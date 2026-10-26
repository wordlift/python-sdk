from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from graphql import print_ast

import wordlift_sdk.kg_build.import_hash_lookup as lookup_module
from wordlift_sdk.kg_build.import_hash_lookup import GraphQlImportHashLookup


class _Session:
    def __init__(self, stored: dict[str, str | None]) -> None:
        self._stored = stored
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def execute(self, query, variable_values):
        self.calls.append((print_ast(query), variable_values))
        return {
            alias: (
                None
                if self._stored.get(iri, "missing") == "missing"
                else {"hash": self._stored[iri]}
            )
            for alias, iri in (
                (f"e{key[1:]}", value) for key, value in variable_values.items()
            )
        }


class _Provider:
    def __init__(self, session: _Session) -> None:
        self._session = session

    @asynccontextmanager
    async def create(self):
        yield self._session


@pytest.mark.asyncio
async def test_import_hashes_maps_only_iris_with_a_stored_hash() -> None:
    session = _Session(
        {
            "https://data.example.com/d/a/1": "hash-a",
            "https://data.example.com/d/b/1": None,
        }
    )
    lookup = GraphQlImportHashLookup(_Provider(session))

    hashes = await lookup.import_hashes(
        [
            "https://data.example.com/d/b/1",
            "https://data.example.com/d/a/1",
            "https://data.example.com/d/c/1",
            "https://data.example.com/d/a/1",
        ]
    )

    assert hashes == {"https://data.example.com/d/a/1": "hash-a"}
    (query, variables) = session.calls[0]
    assert "$i0: Ref!" in query
    assert 'string(name: "seovoc:importHash")' in query
    assert variables == {
        "i0": "https://data.example.com/d/a/1",
        "i1": "https://data.example.com/d/b/1",
        "i2": "https://data.example.com/d/c/1",
    }


@pytest.mark.asyncio
async def test_import_hashes_batches_large_iri_sets(monkeypatch) -> None:
    monkeypatch.setattr(lookup_module, "_BATCH_SIZE", 2)
    iris = [f"https://data.example.com/d/x/{n}" for n in range(5)]
    session = _Session({iri: f"h{n}" for n, iri in enumerate(iris)})
    lookup = GraphQlImportHashLookup(_Provider(session))

    hashes = await lookup.import_hashes(iris)

    assert hashes == {iri: f"h{n}" for n, iri in enumerate(iris)}
    assert [len(variables) for _, variables in session.calls] == [2, 2, 1]


@pytest.mark.asyncio
async def test_import_hashes_without_iris_sends_no_query() -> None:
    session = _Session({})

    assert await GraphQlImportHashLookup(_Provider(session)).import_hashes([]) == {}
    assert session.calls == []

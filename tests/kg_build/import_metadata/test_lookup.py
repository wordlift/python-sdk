from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from graphql import print_ast
from rdflib import Graph, Literal, URIRef
from tenacity import wait_none

import wordlift_sdk.kg_build.import_metadata.lookup as lookup_module
from wordlift_sdk.kg_build.import_metadata import (
    SEOVOC_IMPORT_HASH,
    GraphQlImportHashLookup,
    restore_stored_import_hash,
)

DATASET = "https://data.example.com/dataset"
ORG = f"{DATASET}/organizations/acme"
SITE = f"{DATASET}/web-sites/acme"


class _Session:
    def __init__(self, stored: dict[str, str | None], fail_first: int = 0) -> None:
        self._stored = stored
        self._fail_first = fail_first
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def execute(self, query, variable_values):
        self.calls.append((print_ast(query), variable_values))
        if len(self.calls) <= self._fail_first:
            raise asyncio.TimeoutError()
        return {
            f"e{key[1:]}": (
                {"hash": self._stored[iri]} if self._stored.get(iri) else None
            )
            for key, iri in variable_values.items()
        }


class _Provider:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.opened = 0

    @asynccontextmanager
    async def create(self):
        self.opened += 1
        yield self.session


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        GraphQlImportHashLookup.import_hashes.retry, "wait", wait_none()
    )


@pytest.mark.asyncio
async def test_import_hashes_maps_iris_with_a_stored_hash() -> None:
    provider = _Provider(_Session({ORG: "h", SITE: None}))

    hashes = await GraphQlImportHashLookup(provider).import_hashes([SITE, ORG, ORG])

    assert hashes == {ORG: "h"}
    ((query, variables),) = provider.session.calls
    assert 'resource(iri: $i0) {\n    hash: string(name: "seovoc:importHash")' in query
    assert variables == {"i0": ORG, "i1": SITE}


@pytest.mark.asyncio
async def test_import_hashes_batches_in_one_session(monkeypatch) -> None:
    monkeypatch.setattr(lookup_module, "_BATCH_SIZE", 2)
    iris = [f"{DATASET}/things/{n}" for n in range(5)]
    provider = _Provider(_Session({iri: f"h{n}" for n, iri in enumerate(iris)}))

    hashes = await GraphQlImportHashLookup(provider).import_hashes(iris)

    assert hashes == {iri: f"h{n}" for n, iri in enumerate(iris)}
    assert [len(variables) for _, variables in provider.session.calls] == [2, 2, 1]
    assert provider.opened == 1


@pytest.mark.asyncio
async def test_import_hashes_retries_transient_failures() -> None:
    provider = _Provider(_Session({ORG: "h"}, fail_first=1))

    assert await GraphQlImportHashLookup(provider).import_hashes([ORG]) == {ORG: "h"}
    assert provider.opened == 2


@pytest.mark.asyncio
async def test_import_hashes_without_iris_opens_no_session() -> None:
    provider = _Provider(_Session({}))

    assert await GraphQlImportHashLookup(provider).import_hashes([]) == {}
    assert provider.opened == 0


def _templates() -> Graph:
    graph = Graph()
    graph.add((URIRef(ORG), URIRef("https://schema.org/name"), Literal("Acme")))
    graph.add((URIRef(SITE), URIRef("https://schema.org/publisher"), URIRef(ORG)))
    return graph


def _lookup(**kwargs) -> AsyncMock:
    return AsyncMock(import_hashes=AsyncMock(**kwargs))


@pytest.mark.asyncio
async def test_restore_puts_back_the_hash_all_subjects_share() -> None:
    graph = _templates()

    restored = await restore_stored_import_hash(
        graph, DATASET, _lookup(return_value={ORG: "h", SITE: "h"})
    )

    assert restored is True
    assert set(graph.subject_objects(SEOVOC_IMPORT_HASH)) == {
        (URIRef(ORG), Literal("h")),
        (URIRef(SITE), Literal("h")),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [{}, {ORG: "h"}, {ORG: "h", SITE: "other"}])
async def test_restore_leaves_graph_alone_unless_every_hash_agrees(
    stored: dict[str, str],
) -> None:
    graph = _templates()

    assert not await restore_stored_import_hash(
        graph, DATASET, _lookup(return_value=stored)
    )
    assert not list(graph.subject_objects(SEOVOC_IMPORT_HASH))


@pytest.mark.asyncio
async def test_restore_logs_and_writes_when_lookup_fails(caplog) -> None:
    graph = _templates()

    assert not await restore_stored_import_hash(
        graph, DATASET, _lookup(side_effect=RuntimeError("boom"))
    )
    assert "Stored import hash lookup failed" in caplog.text


@pytest.mark.asyncio
async def test_restore_skips_lookup_for_graph_outside_the_dataset() -> None:
    lookup = _lookup(return_value={})

    assert not await restore_stored_import_hash(
        _templates(), "https://other.example", lookup
    )
    lookup.import_hashes.assert_not_awaited()

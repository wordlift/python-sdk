from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.entity_patcher import EntityPatcher


def _ctx(dataset_uri: str | None):
    return SimpleNamespace(
        account=SimpleNamespace(dataset_uri=dataset_uri),
        entity_patch_queue=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_patch_no_predicates_is_noop() -> None:
    context = _ctx("https://data.example.com")
    patcher = EntityPatcher(context)
    await patcher.patch(URIRef("https://data.example.com/a"), Graph())
    context.entity_patch_queue.put.assert_not_called()


@pytest.mark.asyncio
async def test_patch_creates_remove_add_ops() -> None:
    context = _ctx("https://data.example.com")
    patcher = EntityPatcher(context)
    iri = URIRef("https://data.example.com/a")
    g = Graph()
    pred = URIRef("https://schema.org/name")
    g.add((iri, pred, Literal("A")))
    await patcher.patch(iri, g)
    call = context.entity_patch_queue.put.call_args.args[0]
    assert str(call.iri) == str(iri)
    assert len(call.requests) == 2
    assert call.requests[0].op == "remove"
    assert call.requests[1].op == "add"


@pytest.mark.asyncio
async def test_patch_all_filters_to_dataset_subjects() -> None:
    context = _ctx("https://data.example.com")
    patcher = EntityPatcher(context)
    g = Graph()
    s1 = URIRef("https://data.example.com/a")
    s2 = URIRef("https://external.example.com/b")
    p = URIRef("https://schema.org/name")
    g.add((s1, p, Literal("A")))
    g.add((s2, p, Literal("B")))
    await patcher.patch_all(g)
    assert context.entity_patch_queue.put.await_count == 1


@pytest.mark.asyncio
async def test_patch_all_no_dataset_uri_noop() -> None:
    context = _ctx(None)
    patcher = EntityPatcher(context)
    g = Graph()
    g.add((URIRef("https://x"), URIRef("https://p"), Literal("v")))
    await patcher.patch_all(g)
    context.entity_patch_queue.put.assert_not_called()

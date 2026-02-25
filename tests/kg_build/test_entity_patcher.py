from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.entity_patcher import EntityPatcher, SEOVOC_IMPORT_HASH


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
    assert len(call.requests) == 4
    assert all(request.op in {"remove", "add"} for request in call.requests)
    assert any(request.path == f"/{SEOVOC_IMPORT_HASH}" for request in call.requests)


@pytest.mark.asyncio
async def test_patch_off_mode_does_not_write_import_hash() -> None:
    context = _ctx("https://data.example.com")
    patcher = EntityPatcher(context)
    iri = URIRef("https://data.example.com/a")
    g = Graph()
    pred = URIRef("https://schema.org/name")
    g.add((iri, pred, Literal("A")))

    await patcher.patch(iri, g, import_hash_mode="off")

    call = context.entity_patch_queue.put.call_args.args[0]
    assert len(call.requests) == 2
    assert not any(
        request.path == f"/{SEOVOC_IMPORT_HASH}" for request in call.requests
    )


@pytest.mark.asyncio
async def test_patch_skips_when_existing_import_hash_matches() -> None:
    context = _ctx("https://data.example.com")
    patcher = EntityPatcher(context)
    iri = URIRef("https://data.example.com/a")
    g = Graph()
    pred = URIRef("https://schema.org/name")
    g.add((iri, pred, Literal("A")))
    expected_hash = patcher._compute_import_hash(iri, g)
    g.add((iri, SEOVOC_IMPORT_HASH, Literal(expected_hash)))

    await patcher.patch(iri, g)

    context.entity_patch_queue.put.assert_not_called()
    assert (iri, SEOVOC_IMPORT_HASH, Literal(expected_hash)) in g


@pytest.mark.asyncio
async def test_patch_write_mode_does_not_skip_on_matching_hash() -> None:
    context = _ctx("https://data.example.com")
    patcher = EntityPatcher(context)
    iri = URIRef("https://data.example.com/a")
    g = Graph()
    pred = URIRef("https://schema.org/name")
    g.add((iri, pred, Literal("A")))
    expected_hash = patcher._compute_import_hash(iri, g)
    g.add((iri, SEOVOC_IMPORT_HASH, Literal(expected_hash)))

    await patcher.patch(iri, g, import_hash_mode="write")

    context.entity_patch_queue.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_compute_import_hash_ignores_existing_import_hash_value() -> None:
    patcher = EntityPatcher(_ctx("https://data.example.com"))
    iri = URIRef("https://data.example.com/a")
    pred = URIRef("https://schema.org/name")

    g1 = Graph()
    g1.add((iri, pred, Literal("A")))
    g1.add((iri, SEOVOC_IMPORT_HASH, Literal("old-1")))

    g2 = Graph()
    g2.add((iri, pred, Literal("A")))
    g2.add((iri, SEOVOC_IMPORT_HASH, Literal("old-2")))

    assert patcher._compute_import_hash(iri, g1) == patcher._compute_import_hash(
        iri, g2
    )


def test_compute_import_hash_includes_sibling_subjects() -> None:
    patcher = EntityPatcher(_ctx("https://data.example.com"))
    iri = URIRef("https://data.example.com/a")
    sibling = URIRef("https://data.example.com/b")
    pred = URIRef("https://schema.org/name")

    g1 = Graph()
    g1.add((iri, pred, Literal("A")))
    g1.add((sibling, pred, Literal("B")))

    g2 = Graph()
    g2.add((iri, pred, Literal("A")))
    g2.add((sibling, pred, Literal("B2")))

    assert patcher._compute_import_hash(iri, g1, "https://data.example.com")
    assert patcher._compute_import_hash(
        iri, g1, "https://data.example.com"
    ) != patcher._compute_import_hash(iri, g2, "https://data.example.com")


@pytest.mark.asyncio
async def test_patch_all_skips_all_nodes_when_provided_hash_matches_graph_snapshot() -> (
    None
):
    context = _ctx("https://data.example.com")
    patcher = EntityPatcher(context)
    a = URIRef("https://data.example.com/a")
    b = URIRef("https://data.example.com/b")
    pred = URIRef("https://schema.org/name")
    g = Graph()
    g.add((a, pred, Literal("A")))
    g.add((b, pred, Literal("B")))

    expected = patcher._compute_import_hash(a, g, "https://data.example.com")
    g.add((a, SEOVOC_IMPORT_HASH, Literal(expected)))
    g.add((b, SEOVOC_IMPORT_HASH, Literal(expected)))

    await patcher.patch_all(g)

    context.entity_patch_queue.put.assert_not_called()


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

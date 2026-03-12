from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from rdflib import Graph, Literal, URIRef
from wordlift_client.exceptions import ApiException

from wordlift_sdk.kg_build.entity_patcher import (
    EntityPatcher,
    SEOVOC_IMPORT_HASH,
)


def _ctx(
    dataset_uri: str | None,
    patch_concurrency: int = 10,
    patch_concurrency_max: int = 20,
):
    return SimpleNamespace(
        account=SimpleNamespace(dataset_uri=dataset_uri),
        entity_patch_queue=AsyncMock(),
        patch_concurrency=patch_concurrency,
        patch_concurrency_max=patch_concurrency_max,
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
async def test_patch_all_skips_child_nodes_when_first_level_hash_matches() -> None:
    context = _ctx("https://data.example.com/dataset")
    patcher = EntityPatcher(context)
    page = URIRef("https://data.example.com/dataset/web-pages/1")
    article = URIRef("https://data.example.com/dataset/entities/article-1")
    child = URIRef("https://data.example.com/dataset/entities/article-1/faq/1")
    g = Graph()
    g.add((page, URIRef("https://schema.org/mainEntity"), article))
    g.add((page, URIRef("https://schema.org/name"), Literal("Page 1")))
    g.add((article, URIRef("https://schema.org/headline"), Literal("Hello")))
    g.add((article, URIRef("https://schema.org/hasPart"), child))
    g.add((child, URIRef("https://schema.org/name"), Literal("Child FAQ")))

    expected = patcher._compute_import_hash(page, g, "https://data.example.com/dataset")
    g.add((page, SEOVOC_IMPORT_HASH, Literal(expected)))
    g.add((article, SEOVOC_IMPORT_HASH, Literal(expected)))

    await patcher.patch_all(g)

    context.entity_patch_queue.put.assert_not_called()


@pytest.mark.asyncio
async def test_patch_all_sends_deep_child_entity_when_graph_changes() -> None:
    context = _ctx("https://data.example.com/dataset")
    patcher = EntityPatcher(context)
    page = URIRef("https://data.example.com/dataset/web-pages/1")
    article = URIRef("https://data.example.com/dataset/entities/article-1")
    child = URIRef("https://data.example.com/dataset/entities/article-1/children/1")
    g = Graph()
    g.add((page, URIRef("https://schema.org/mainEntity"), article))
    g.add((page, URIRef("https://schema.org/name"), Literal("Page 1")))
    g.add((article, URIRef("https://schema.org/headline"), Literal("Hello")))
    g.add((article, URIRef("https://schema.org/hasPart"), child))
    g.add((child, URIRef("https://schema.org/name"), Literal("Child Node")))

    await patcher.patch_all(g)

    patched_iris = {
        str(call.args[0].iri) for call in context.entity_patch_queue.put.await_args_list
    }
    assert str(child) in patched_iris


@pytest.mark.asyncio
async def test_patch_all_treats_child_only_graph_as_first_level_fallback() -> None:
    context = _ctx("https://data.example.com/dataset")
    patcher = EntityPatcher(context)
    child = URIRef("https://data.example.com/dataset/entities/article-1/children/1")
    g = Graph()
    g.add((child, URIRef("https://schema.org/name"), Literal("Child Node")))

    await patcher.patch_all(g)

    patched_iris = {
        str(call.args[0].iri) for call in context.entity_patch_queue.put.await_args_list
    }
    assert patched_iris == {str(child)}


@pytest.mark.asyncio
async def test_patch_all_skips_child_only_graph_when_fallback_hash_matches() -> None:
    context = _ctx("https://data.example.com/dataset")
    patcher = EntityPatcher(context)
    child = URIRef("https://data.example.com/dataset/entities/article-1/children/1")
    g = Graph()
    g.add((child, URIRef("https://schema.org/name"), Literal("Child Node")))
    expected = patcher._compute_import_hash(
        child, g, "https://data.example.com/dataset"
    )
    g.add((child, SEOVOC_IMPORT_HASH, Literal(expected)))

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


# ---------------------------------------------------------------------------
# Adaptive concurrency tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_all_concurrent_each_iri_patched_exactly_once() -> None:
    """All IRIs are patched exactly once with concurrency > 1."""
    context = _ctx("https://data.example.com", patch_concurrency=5)
    patcher = EntityPatcher(context)
    p = URIRef("https://schema.org/name")
    g = Graph()
    iris = [URIRef(f"https://data.example.com/{i}") for i in range(10)]
    for iri in iris:
        g.add((iri, p, Literal(str(iri))))

    await patcher.patch_all(g)

    patched_iris = {
        str(call.args[0].iri) for call in context.entity_patch_queue.put.await_args_list
    }
    assert patched_iris == {str(iri) for iri in iris}
    assert context.entity_patch_queue.put.await_count == len(iris)


@pytest.mark.asyncio
async def test_patch_all_concurrency_is_respected() -> None:
    """At most N tasks run simultaneously when concurrency=N."""
    concurrency = 3
    context = _ctx("https://data.example.com", patch_concurrency=concurrency)
    patcher = EntityPatcher(context)

    concurrent_peak = 0
    current = 0

    original_put = context.entity_patch_queue.put

    async def slow_put(entity_patch):
        nonlocal concurrent_peak, current
        current += 1
        concurrent_peak = max(concurrent_peak, current)
        await asyncio.sleep(0)  # yield to let other tasks start
        await original_put(entity_patch)
        current -= 1

    context.entity_patch_queue.put = slow_put

    p = URIRef("https://schema.org/name")
    g = Graph()
    for i in range(12):
        g.add((URIRef(f"https://data.example.com/{i}"), p, Literal(str(i))))

    await patcher.patch_all(g)

    assert concurrent_peak <= concurrency


@pytest.mark.asyncio
async def test_patch_all_step_down_on_rate_limit_error() -> None:
    """Semaphore is halved when a 429 error is raised."""
    context = _ctx("https://data.example.com", patch_concurrency=8)
    patcher = EntityPatcher(context)
    initial_limit = patcher._semaphore.limit

    call_count = 0

    async def failing_then_ok(entity_patch):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            exc = ApiException(status=429, reason="Too Many Requests")
            raise exc

    context.entity_patch_queue.put = failing_then_ok

    p = URIRef("https://schema.org/name")
    g = Graph()
    iri = URIRef("https://data.example.com/a")
    g.add((iri, p, Literal("A")))

    # Patch single IRI so step-down occurs on first call, retry succeeds.
    with patch("wordlift_sdk.kg_build.entity_patcher._STEP_DOWN_BACKOFF", 0):
        await patcher.patch_all(g)

    assert patcher._semaphore.limit == max(1, initial_limit // 2)


@pytest.mark.asyncio
async def test_patch_all_step_down_on_server_error() -> None:
    """Semaphore is halved when a 500 error is raised."""
    context = _ctx("https://data.example.com", patch_concurrency=8)
    patcher = EntityPatcher(context)
    initial_limit = patcher._semaphore.limit

    call_count = 0

    async def failing_then_ok(entity_patch):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ApiException(status=503, reason="Service Unavailable")

    context.entity_patch_queue.put = failing_then_ok

    p = URIRef("https://schema.org/name")
    g = Graph()
    g.add((URIRef("https://data.example.com/a"), p, Literal("A")))

    with patch("wordlift_sdk.kg_build.entity_patcher._STEP_DOWN_BACKOFF", 0):
        await patcher.patch_all(g)

    assert patcher._semaphore.limit == max(1, initial_limit // 2)


@pytest.mark.asyncio
async def test_patch_all_step_up_after_sustained_success() -> None:
    """Semaphore steps up after the configured number of successful batches."""
    context = _ctx(
        "https://data.example.com",
        patch_concurrency=5,
        patch_concurrency_max=10,
    )
    patcher = EntityPatcher(context)
    initial_limit = patcher._semaphore.limit
    step_up_after = patcher._semaphore._step_up_after

    p = URIRef("https://schema.org/name")

    # Run step_up_after successful patch_all batches.
    for i in range(step_up_after):
        g = Graph()
        g.add((URIRef(f"https://data.example.com/{i}"), p, Literal(str(i))))
        await patcher.patch_all(g)

    assert patcher._semaphore.limit == initial_limit + 1


@pytest.mark.asyncio
async def test_patch_all_concurrency_1_is_sequential() -> None:
    """When concurrency=1, behaviour is identical to the original sequential loop."""
    context = _ctx("https://data.example.com", patch_concurrency=1)
    patcher = EntityPatcher(context)

    call_order: list[str] = []

    async def recording_put(entity_patch):
        call_order.append(str(entity_patch.iri))

    context.entity_patch_queue.put = recording_put

    p = URIRef("https://schema.org/name")
    iris = [URIRef(f"https://data.example.com/{i}") for i in range(5)]
    g = Graph()
    for iri in iris:
        g.add((iri, p, Literal(str(iri))))

    await patcher.patch_all(g)

    # All IRIs patched exactly once; order is determined by set iteration
    # (same as the old sequential loop).
    assert sorted(call_order) == sorted(str(iri) for iri in iris)
    assert len(call_order) == len(iris)

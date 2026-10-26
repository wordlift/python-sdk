from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from rdflib import Graph, Literal, URIRef
from wordlift_client.exceptions import ApiException

from wordlift_sdk.kg_build.entity_patcher import (
    SEOVOC_IMPORT_HASH,
    EntityPatcher,
    _AdaptiveConcurrency,
)
from wordlift_sdk.kg_build.import_metadata import compute_import_hash


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
    expected_hash = compute_import_hash(g, iri)
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
    expected_hash = compute_import_hash(g, iri)
    g.add((iri, SEOVOC_IMPORT_HASH, Literal(expected_hash)))

    await patcher.patch(iri, g, import_hash_mode="write")

    context.entity_patch_queue.put.assert_awaited_once()


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

    expected = compute_import_hash(g, a, "https://data.example.com")
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

    expected = compute_import_hash(g, page, "https://data.example.com/dataset")
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
    expected = compute_import_hash(g, child, "https://data.example.com/dataset")
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


_NAME = URIRef("https://schema.org/name")


def _graph(*iris: str) -> Graph:
    g = Graph()
    for iri in iris:
        g.add((URIRef(iri), _NAME, Literal(iri)))
    return g


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ApiException(status=429, reason="Too Many Requests"),
        ApiException(status=503, reason="Service Unavailable"),
        asyncio.TimeoutError(),
    ],
    ids=["429", "503", "timeout"],
)
async def test_patch_all_transient_error_steps_down_without_extra_retry(
    error: BaseException,
) -> None:
    """A transient error halves the limit and propagates: the queue retried it."""
    context = _ctx("https://data.example.com", patch_concurrency=8)
    context.entity_patch_queue.put = AsyncMock(side_effect=error)
    patcher = EntityPatcher(context)

    with pytest.raises(type(error)):
        await patcher.patch_all(_graph("https://data.example.com/a"))

    assert patcher._concurrency.limit == 4
    assert patcher._concurrency.in_flight == 0
    assert context.entity_patch_queue.put.await_count == 1


@pytest.mark.asyncio
async def test_patch_all_failure_cancels_and_awaits_sibling_patches() -> None:
    """No sibling patch is left running once patch_all raises."""
    context = _ctx("https://data.example.com", patch_concurrency=5)
    patcher = EntityPatcher(context)
    failing = "https://data.example.com/fail"
    siblings = [f"https://data.example.com/{i}" for i in range(4)]
    started: list[str] = []
    cancelled: list[str] = []
    all_started = asyncio.Event()

    async def put(entity_patch):
        iri = str(entity_patch.iri)
        if iri == failing:
            await all_started.wait()
            raise ApiException(status=400, reason="Bad Request")
        started.append(iri)
        if len(started) == len(siblings):
            all_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(iri)
            raise

    context.entity_patch_queue.put = put

    with pytest.raises(ApiException):
        await asyncio.wait_for(patcher.patch_all(_graph(failing, *siblings)), 1)

    assert sorted(cancelled) == sorted(siblings)
    assert patcher._concurrency.in_flight == 0
    assert patcher._concurrency.limit == 5  # a 400 is not an overload


async def _hold(concurrency: _AdaptiveConcurrency, release: asyncio.Event) -> None:
    await concurrency.limited(release.wait)()


@pytest.mark.asyncio
async def test_adaptive_concurrency_step_down_while_held_does_not_drift() -> None:
    """Permits held across a step-down are returned without raising the limit."""
    concurrency = _AdaptiveConcurrency(initial=4, maximum=4)
    first_wave = asyncio.Event()
    holders = [asyncio.ensure_future(_hold(concurrency, first_wave)) for _ in range(4)]
    await asyncio.sleep(0)
    assert concurrency.in_flight == 4

    concurrency.step_down()
    first_wave.set()
    await asyncio.gather(*holders)
    assert concurrency.limit == 2
    assert concurrency.in_flight == 0

    second_wave = asyncio.Event()
    holders = [asyncio.ensure_future(_hold(concurrency, second_wave)) for _ in range(3)]
    await asyncio.sleep(0)
    assert concurrency.in_flight == 2

    second_wave.set()
    await asyncio.wait_for(asyncio.gather(*holders), 1)


@pytest.mark.asyncio
async def test_adaptive_concurrency_step_up_wakes_waiter() -> None:
    concurrency = _AdaptiveConcurrency(initial=1, maximum=2, step_up_after=1)
    release = asyncio.Event()
    holders = [asyncio.ensure_future(_hold(concurrency, release)) for _ in range(2)]
    await asyncio.sleep(0)
    assert concurrency.in_flight == 1

    concurrency.record_batch_success()
    await asyncio.sleep(0)

    assert concurrency.limit == 2
    assert concurrency.in_flight == 2
    release.set()
    await asyncio.wait_for(asyncio.gather(*holders), 1)


@pytest.mark.asyncio
async def test_adaptive_concurrency_cancelled_waiter_takes_no_permit() -> None:
    concurrency = _AdaptiveConcurrency(initial=1, maximum=1)
    release = asyncio.Event()
    holder = asyncio.ensure_future(_hold(concurrency, release))
    waiter = asyncio.ensure_future(_hold(concurrency, release))
    await asyncio.sleep(0)

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await holder

    assert concurrency.in_flight == 0


@pytest.mark.asyncio
async def test_patch_all_step_up_after_sustained_success() -> None:
    """The limit steps up after the configured number of successful batches."""
    context = _ctx(
        "https://data.example.com",
        patch_concurrency=5,
        patch_concurrency_max=10,
    )
    patcher = EntityPatcher(context)
    step_up_after = patcher._concurrency._step_up_after

    for i in range(step_up_after):
        await patcher.patch_all(_graph(f"https://data.example.com/{i}"))

    assert patcher._concurrency.limit == 6


@pytest.mark.asyncio
async def test_patch_all_recovers_after_stepping_down_to_one() -> None:
    """A limit stepped down to 1 still steps back up on sustained success."""
    context = _ctx("https://data.example.com", patch_concurrency=2)
    patcher = EntityPatcher(context)
    patcher._concurrency.step_down()
    patcher._concurrency.step_down()  # already at the floor
    assert patcher._concurrency.limit == 1

    for i in range(patcher._concurrency._step_up_after):
        await patcher.patch_all(_graph(f"https://data.example.com/{i}"))

    assert patcher._concurrency.limit == 2


@pytest.mark.asyncio
async def test_patch_all_concurrency_1_is_sequential() -> None:
    """With concurrency=1 every IRI is patched once, one at a time."""
    context = _ctx("https://data.example.com", patch_concurrency=1)
    patcher = EntityPatcher(context)
    call_order: list[str] = []
    current = peak = 0

    async def recording_put(entity_patch):
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        call_order.append(str(entity_patch.iri))
        await asyncio.sleep(0)
        current -= 1

    context.entity_patch_queue.put = recording_put
    iris = [f"https://data.example.com/{i}" for i in range(5)]

    await patcher.patch_all(_graph(*iris))

    assert sorted(call_order) == sorted(iris)
    assert peak == 1

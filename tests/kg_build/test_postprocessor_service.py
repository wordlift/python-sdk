from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.postprocessors.service import PostprocessorService
from wordlift_sdk.kg_build.postprocessors.types import (
    LoadedPostprocessor,
    PostprocessorContext,
)


def _sample_graph() -> Graph:
    g = Graph()
    g.add(
        (
            URIRef("https://example.com/s"),
            URIRef("https://example.com/p"),
            Literal("v"),
        )
    )
    return g


def _sample_context() -> PostprocessorContext:
    return PostprocessorContext(
        profile_name="test",
        profile={},
        url="https://example.com/page",
        account=SimpleNamespace(dataset_uri="https://data.example.com"),
        account_key=None,
        exports={},
        response=SimpleNamespace(
            id=None, web_page=SimpleNamespace(url=None, html=None)
        ),
        existing_web_page_id=None,
    )


def _make_service(pool_size: int = 1, processors=None) -> PostprocessorService:
    if processors is None:

        class _Passthrough:
            def process_graph(self, graph: Graph, context) -> Graph:
                return graph

        processors = [LoadedPostprocessor(name="passthrough", handler=_Passthrough())]

    return PostprocessorService(
        postprocessors_factory=lambda: processors,
        pool_size=pool_size,
    )


def test_apply_returns_result_with_graph_and_timings() -> None:
    service = _make_service()
    result = asyncio.run(service.apply(_sample_graph(), _sample_context()))
    service.close()

    assert isinstance(result.graph, Graph)
    assert len(result.graph) == 1
    assert result.queue_wait_ms >= 0
    assert result.postprocessors_ms >= 0


def test_apply_runs_processors_in_order() -> None:
    additions: list[int] = []

    class _Mark:
        def __init__(self, n: int) -> None:
            self._n = n

        def process_graph(self, graph: Graph, context) -> Graph:
            additions.append(self._n)
            graph.add(
                (
                    URIRef(f"https://example.com/s{self._n}"),
                    URIRef("https://example.com/p"),
                    Literal(self._n),
                )
            )
            return graph

    processors = [
        LoadedPostprocessor(name="first", handler=_Mark(1)),
        LoadedPostprocessor(name="second", handler=_Mark(2)),
    ]
    service = PostprocessorService(
        postprocessors_factory=lambda: processors,
        pool_size=1,
    )
    result = asyncio.run(service.apply(_sample_graph(), _sample_context()))
    service.close()

    assert additions == [1, 2]
    assert len(result.graph) == 3  # original + 2 added


def test_close_calls_close_on_closeable_handlers() -> None:
    class _Closeable:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

        def process_graph(self, graph: Graph, context) -> Graph:
            return graph

    handler = _Closeable()
    service = PostprocessorService(
        postprocessors_factory=lambda: [LoadedPostprocessor(name="c", handler=handler)],
        pool_size=1,
    )
    service.close()

    assert handler.closed is True


def test_pool_isolates_slots() -> None:
    """Each slot in the pool should be an independent list of processors."""
    slot_ids: list[int] = []

    class _Recorder:
        def __init__(self, slot_id: int) -> None:
            self._slot_id = slot_id

        def process_graph(self, graph: Graph, context) -> Graph:
            slot_ids.append(self._slot_id)
            return graph

    slot_counter = [0]

    def factory() -> list[LoadedPostprocessor]:
        slot_counter[0] += 1
        sid = slot_counter[0]
        return [LoadedPostprocessor(name=f"slot-{sid}", handler=_Recorder(sid))]

    pool_size = 2
    service = PostprocessorService(postprocessors_factory=factory, pool_size=pool_size)
    try:
        # Run both slots sequentially
        asyncio.run(service.apply(_sample_graph(), _sample_context()))
        asyncio.run(service.apply(_sample_graph(), _sample_context()))
    finally:
        service.close()

    # Both slots should have been used (order may vary but both IDs present)
    assert len(slot_ids) == 2
    assert set(slot_ids) == {1, 2}


@pytest.mark.asyncio
async def test_apply_async_returns_correct_graph() -> None:
    service = _make_service()
    graph = _sample_graph()
    result = await service.apply(graph, _sample_context())
    service.close()

    assert isinstance(result.graph, Graph)
    assert len(result.graph) == 1

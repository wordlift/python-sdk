from __future__ import annotations

import asyncio
import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterable
from typing import Callable

from rdflib import Graph

from .graph_io import close_loaded_postprocessors
from .types import LoadedPostprocessor, PostprocessorContext, PostprocessorResult

logger = logging.getLogger(__name__)


class PostprocessorService:
    """Executes an ordered list of postprocessors against a graph.

    Completely agnostic to profiles and pipeline composition — callers are
    responsible for assembling the postprocessor list and building the context.
    """

    def __init__(
        self,
        *,
        postprocessors_factory: Callable[[], Iterable[LoadedPostprocessor]],
        pool_size: int,
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=pool_size, thread_name_prefix="worai_pp"
        )
        self._queue: asyncio.Queue = asyncio.Queue()
        for _ in range(pool_size):
            self._queue.put_nowait(postprocessors_factory())
        logger.info("Created postprocessor pool (pool_size=%d)", pool_size)

    async def apply(
        self,
        graph: Graph,
        context: PostprocessorContext,
    ) -> PostprocessorResult:
        _t1 = time.perf_counter()
        postprocessors = await self._queue.get()
        queue_wait_ms = int((time.perf_counter() - _t1) * 1000)
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                self._executor,
                functools.partial(
                    self._run, graph, context, postprocessors, queue_wait_ms
                ),
            )
        finally:
            self._queue.put_nowait(postprocessors)

    def close(self) -> None:
        while not self._queue.empty():
            try:
                close_loaded_postprocessors(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        self._executor.shutdown(wait=False)

    def _run(
        self,
        graph: Graph,
        context: PostprocessorContext,
        postprocessors: Iterable[LoadedPostprocessor],
        queue_wait_ms: int,
    ) -> PostprocessorResult:
        _t_start = time.perf_counter()
        for processor in postprocessors:
            _tp = time.perf_counter()
            graph = processor.run(graph, context)
            logger.info(
                "Applied postprocessor '%s' for %s [%dms]",
                processor.name,
                context.url,
                int((time.perf_counter() - _tp) * 1000),
            )
        return PostprocessorResult(
            graph=graph,
            queue_wait_ms=queue_wait_ms,
            postprocessors_ms=int((time.perf_counter() - _t_start) * 1000),
        )

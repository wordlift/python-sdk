from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import anyio
from rdflib import Graph, URIRef
from wordlift_client.models.entity_patch_request import EntityPatchRequest
from wordlift_sdk.protocol import Context
from wordlift_sdk.protocol.entity_patch import EntityPatch
from wordlift_sdk.protocol.errors import is_transient_error

from .import_metadata import (
    SEOVOC_IMPORT_HASH as SEOVOC_IMPORT_HASH,  # re-exported for existing importers
    ImportWritePlanner,
    compute_import_hash,
    set_import_hash,
    stored_import_hash,
)

logger = logging.getLogger(__name__)

_STEP_UP_AFTER = 20  # consecutive successful patch_all calls before step-up

_P = ParamSpec("_P")
_R = TypeVar("_R")


class _AdaptiveConcurrency:
    """Adaptive policy over an ``anyio.CapacityLimiter``.

    - Steps down (halves) on a transient error (transport, 429, 5xx), minimum
      1. ``EntityPatchQueue`` has already retried it, so it is not retried here.
    - Steps up (increments by 1) after ``step_up_after`` consecutive
      successful patch_all batches, up to ``maximum``.

    The limiter keeps permits already held when its limit changes, so the
    limit never drifts.
    """

    def __init__(
        self, initial: int, maximum: int, step_up_after: int = _STEP_UP_AFTER
    ) -> None:
        self._limiter = anyio.CapacityLimiter(max(1, initial))
        self._maximum = max(self.limit, maximum)
        self._step_up_after = step_up_after
        self._consecutive_successes = 0

    @property
    def limit(self) -> int:
        return int(self._limiter.total_tokens)

    @property
    def in_flight(self) -> int:
        return self._limiter.borrowed_tokens

    def limited(self, fn: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        """Run ``fn`` under the limit; step down when it hits a transient error."""

        @functools.wraps(fn)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            async with self._limiter:
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    if is_transient_error(exc):
                        self.step_down()
                    raise

        return wrapper

    def step_down(self) -> None:
        new_limit = max(1, self.limit // 2)
        if new_limit < self.limit:
            self._limiter.total_tokens = new_limit
            logger.warning("Adaptive patch concurrency stepped down to %d", new_limit)
        self._consecutive_successes = 0

    def record_batch_success(self) -> None:
        self._consecutive_successes += 1
        if (
            self._consecutive_successes >= self._step_up_after
            and self.limit < self._maximum
        ):
            self._limiter.total_tokens = self.limit + 1
            self._consecutive_successes = 0
            logger.info("Adaptive patch concurrency stepped up to %d", self.limit)


class EntityPatcher:
    """Queue entity patches from an RDFLib graph."""

    def __init__(
        self, context: Context, planner: ImportWritePlanner | None = None
    ) -> None:
        self._context = context
        self._planner = planner or ImportWritePlanner()
        concurrency = getattr(context, "patch_concurrency", 10)
        max_concurrency = getattr(context, "patch_concurrency_max", 20)
        self._concurrency = _AdaptiveConcurrency(
            initial=concurrency, maximum=max_concurrency
        )
        self._patch_limited = self._concurrency.limited(self.patch)

    async def patch(
        self, iri: URIRef, graph: Graph, import_hash_mode: str = "on"
    ) -> None:
        dataset_uri = str(
            getattr(self._context.account, "dataset_uri", "") or ""
        ).rstrip("/")
        non_hash_predicates = {
            predicate
            for _, predicate, _ in graph.triples((iri, None, None))
            if predicate != SEOVOC_IMPORT_HASH
        }
        if not non_hash_predicates:
            return

        # Kept for callers of patch() alone; patch_all() leaves hashing to the
        # ImportWritePlanner and patches every subject with mode "off".
        if import_hash_mode != "off":
            existing_hash = stored_import_hash(graph, iri)
            import_hash = compute_import_hash(graph, iri, dataset_uri)
            set_import_hash(graph, iri, import_hash)
            if (
                import_hash_mode == "on"
                and existing_hash
                and existing_hash == import_hash
            ):
                return

        predicates = {predicate for _, predicate, _ in graph.triples((iri, None, None))}
        if not predicates:
            return

        patches: list[EntityPatchRequest] = []
        for predicate in predicates:
            path = f"/{predicate}"

            mini_graph = Graph()
            for _, _, obj in graph.triples((iri, predicate, None)):
                mini_graph.add((iri, predicate, obj))

            json_ld = mini_graph.serialize(format="json-ld", auto_compact=True)
            patches.append(EntityPatchRequest(op="remove", path=path))
            patches.append(EntityPatchRequest(op="add", path=path, value=json_ld))

        await self._context.entity_patch_queue.put(EntityPatch(iri, patches))

    async def patch_all(self, graph: Graph, import_hash_mode: str = "on") -> None:
        dataset_uri = str(getattr(self._context.account, "dataset_uri", "") or "")
        # The planner stamps the hashes, so each subject is patched as it stands.
        subjects = self._planner.plan(graph, dataset_uri, import_hash_mode)
        if not subjects:
            return

        tasks = [
            asyncio.ensure_future(
                self._patch_limited(iri, graph, import_hash_mode="off")
            )
            for iri in subjects
        ]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            # gather re-raises the first failure with siblings still running:
            # cancel them and wait, so no patch outlives patch_all.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        self._concurrency.record_batch_success()

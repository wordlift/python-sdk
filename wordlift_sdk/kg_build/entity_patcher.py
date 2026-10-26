from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from typing import ParamSpec, TypeVar

import anyio
from rdflib import Graph, Literal, URIRef
from wordlift_client.models.entity_patch_request import EntityPatchRequest
from wordlift_sdk.protocol import Context
from wordlift_sdk.protocol.entity_patch import EntityPatch
from wordlift_sdk.protocol.errors import is_transient_error

logger = logging.getLogger(__name__)

SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")
SEOVOC_DATE_IMPORTED = URIRef("https://w3id.org/seovoc/dateImported")
# Write bookkeeping, not content: neither one feeds the import hash.
IMPORT_METADATA_PREDICATES = frozenset({SEOVOC_IMPORT_HASH, SEOVOC_DATE_IMPORTED})

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
        self,
        context: Context,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._context = context
        self._clock = clock
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
        content_predicates = {
            predicate
            for _, predicate, _ in graph.triples((iri, None, None))
            if predicate not in IMPORT_METADATA_PREDICATES
        }
        if not content_predicates:
            return

        if import_hash_mode != "off":
            existing_hash = self._existing_import_hash(iri, graph)
            import_hash = self._compute_import_hash(iri, graph, dataset_uri)
            self._set_import_hash(iri, graph, import_hash)
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
        dataset_uri = getattr(self._context.account, "dataset_uri", None)
        if not dataset_uri:
            return

        subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(dataset_uri)
        }

        if not subjects:
            return

        subject_modes = {iri: import_hash_mode for iri in subjects}
        first_level_subjects = self._first_level_subjects(graph, dataset_uri)

        if import_hash_mode != "off" and first_level_subjects:
            representative = next(iter(first_level_subjects))
            existing_hash = self._existing_import_hash(representative, graph)
            import_hash = self._compute_import_hash(
                representative, graph, str(dataset_uri).rstrip("/")
            )
            for iri in first_level_subjects:
                self._set_import_hash(iri, graph, import_hash)
            if (
                import_hash_mode == "on"
                and existing_hash
                and existing_hash == import_hash
            ):
                return
            for iri in subjects - first_level_subjects:
                graph.remove((iri, SEOVOC_IMPORT_HASH, None))
                subject_modes[iri] = "off"
            for iri in first_level_subjects:
                subject_modes[iri] = "write"

        self.stamp_date_imported(first_level_subjects, graph)
        tasks = [
            asyncio.ensure_future(
                self._patch_limited(iri, graph, import_hash_mode=subject_modes[iri])
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

    @staticmethod
    def _first_level_subjects(graph: Graph, dataset_uri: str) -> set[URIRef]:
        base = str(dataset_uri or "").rstrip("/")
        subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(f"{base}/")
        }
        if not subjects:
            return set()

        first_level_by_id = {
            subject
            for subject in subjects
            if len([part for part in str(subject)[len(base) + 1 :].split("/") if part])
            == 2
        }
        if first_level_by_id:
            return first_level_by_id

        referenced = {
            obj
            for _, _, obj in graph.triples((None, None, None))
            if isinstance(obj, URIRef) and obj in subjects
        }
        first_level = subjects - referenced
        return first_level or subjects

    def stamp_date_imported(self, subjects: Iterable[URIRef], graph: Graph) -> None:
        """Record on *subjects* that they are being written now.

        Call it only once a write is certain: a skipped write must keep the
        stored date, so ``seovoc:dateImported`` tells when the content changed.
        """
        now = Literal(self._clock().astimezone(timezone.utc).replace(microsecond=0))
        for iri in subjects:
            graph.set((iri, SEOVOC_DATE_IMPORTED, now))

    @staticmethod
    def _existing_import_hash(iri: URIRef, graph: Graph) -> str | None:
        for obj in graph.objects(iri, SEOVOC_IMPORT_HASH):
            value = str(obj).strip()
            if value:
                return value
        return None

    @staticmethod
    def _set_import_hash(iri: URIRef, graph: Graph, import_hash: str) -> None:
        graph.remove((iri, SEOVOC_IMPORT_HASH, None))
        graph.add((iri, SEOVOC_IMPORT_HASH, Literal(import_hash)))

    @staticmethod
    def _compute_import_hash(iri: URIRef, graph: Graph, dataset_uri: str = "") -> str:
        sibling_subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef)
            and (not dataset_uri or str(subject).startswith(dataset_uri))
        }
        sibling_subjects.add(iri)

        terms: list[str] = []
        for subject in sibling_subjects:
            for _, predicate, obj in graph.triples((subject, None, None)):
                if predicate in IMPORT_METADATA_PREDICATES:
                    continue
                terms.append(f"{subject.n3()} {predicate.n3()} {obj.n3()}")
        digest_input = "\n".join(sorted(terms))
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

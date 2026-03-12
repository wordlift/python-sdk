from __future__ import annotations

import asyncio
import hashlib
import logging

from rdflib import Graph, Literal, URIRef
from wordlift_client.models.entity_patch_request import EntityPatchRequest
from wordlift_sdk.protocol import Context
from wordlift_sdk.protocol.entity_patch import EntityPatch

logger = logging.getLogger(__name__)

SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")

_STEP_DOWN_BACKOFF = 1.0  # seconds to wait after a rate-limit step-down
_STEP_UP_AFTER = 20  # consecutive successful patch_all calls before step-up


def _is_rate_limit_or_server_error(exc: BaseException) -> bool:
    """Return True for HTTP 429 and 5xx errors."""
    status = getattr(exc, "status", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


class _AdaptiveSemaphore:
    """asyncio.Semaphore wrapper with adaptive concurrency.

    - Steps down (halves) on rate-limit / server errors, minimum 1.
    - Steps up (increments by 1) after ``step_up_after`` consecutive
      successful patch_all batches, up to ``maximum``.
    """

    def __init__(
        self, initial: int, maximum: int, step_up_after: int = _STEP_UP_AFTER
    ) -> None:
        self._limit = max(1, initial)
        self._maximum = max(self._limit, maximum)
        self._step_up_after = step_up_after
        self._consecutive_successes = 0
        self._semaphore = asyncio.Semaphore(self._limit)
        self._lock = asyncio.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    async def __aenter__(self) -> _AdaptiveSemaphore:
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, *args: object) -> None:
        self._semaphore.release()

    async def step_down(self) -> None:
        async with self._lock:
            new_limit = max(1, self._limit // 2)
            if new_limit < self._limit:
                self._limit = new_limit
                self._semaphore = asyncio.Semaphore(new_limit)
                logger.warning(
                    "Adaptive patch concurrency stepped down to %d", new_limit
                )
            self._consecutive_successes = 0

    async def record_batch_success(self) -> None:
        async with self._lock:
            self._consecutive_successes += 1
            if (
                self._consecutive_successes >= self._step_up_after
                and self._limit < self._maximum
            ):
                self._limit = min(self._limit + 1, self._maximum)
                self._semaphore = asyncio.Semaphore(self._limit)
                self._consecutive_successes = 0
                logger.info("Adaptive patch concurrency stepped up to %d", self._limit)


class EntityPatcher:
    """Queue entity patches from an RDFLib graph."""

    def __init__(self, context: Context) -> None:
        self._context = context
        concurrency = getattr(context, "patch_concurrency", 10)
        max_concurrency = getattr(context, "patch_concurrency_max", 20)
        self._semaphore = _AdaptiveSemaphore(
            initial=concurrency, maximum=max_concurrency
        )

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

        semaphore = self._semaphore

        if semaphore.limit == 1:
            # Preserve exact sequential behaviour when concurrency=1.
            for iri in subjects:
                await self.patch(iri, graph, import_hash_mode=import_hash_mode)
            return

        batch_error: list[BaseException] = []

        async def _patch_one(iri: URIRef) -> None:
            async with semaphore:
                try:
                    await self.patch(iri, graph, import_hash_mode=import_hash_mode)
                except BaseException as exc:
                    if _is_rate_limit_or_server_error(exc):
                        await semaphore.step_down()
                        await asyncio.sleep(_STEP_DOWN_BACKOFF)
                        # One retry after backoff with the reduced semaphore.
                        async with semaphore:
                            await self.patch(
                                iri, graph, import_hash_mode=import_hash_mode
                            )
                    else:
                        batch_error.append(exc)
                        raise

        await asyncio.gather(*(_patch_one(iri) for iri in subjects))

        if not batch_error:
            await semaphore.record_batch_success()

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
                if predicate == SEOVOC_IMPORT_HASH:
                    continue
                terms.append(f"{subject.n3()} {predicate.n3()} {obj.n3()}")
        digest_input = "\n".join(sorted(terms))
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

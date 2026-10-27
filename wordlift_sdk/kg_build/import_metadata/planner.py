from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from rdflib import Graph, Literal, URIRef

from .hashing import compute_import_hash, set_import_hash, stored_import_hash
from .subjects import dataset_subjects, import_subjects
from .vocab import SEOVOC_DATE_IMPORTED, SEOVOC_IMPORT_HASH


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImportWritePlanner:
    """Decide whether a graph is written, and stamp its import metadata.

    The one place both write strategies (``put`` and ``patch``) ask. With
    ``import_hash_mode`` ``on`` an unchanged graph is skipped; ``write`` stamps
    the hash without skipping; ``off`` leaves the hash out. A graph that is
    written gets ``seovoc:dateImported``; a skipped one keeps its stored date,
    so the date tells when the content last changed.
    """

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock

    def plan(
        self, graph: Graph, dataset_uri: str, import_hash_mode: str = "on"
    ) -> frozenset[URIRef]:
        """Stamp import metadata on *graph*; return the subjects to write, if any."""
        subjects = dataset_subjects(graph, dataset_uri) if dataset_uri else set()
        if not subjects:
            return frozenset()
        roots = import_subjects(graph, dataset_uri)

        if import_hash_mode != "off":
            representative = min(roots, key=str)
            stored = stored_import_hash(graph, representative)
            current = compute_import_hash(
                graph, representative, dataset_uri.rstrip("/")
            )
            for subject in subjects - roots:
                graph.remove((subject, SEOVOC_IMPORT_HASH, None))
            for subject in roots:
                set_import_hash(graph, subject, current)
            if import_hash_mode == "on" and stored == current:
                return frozenset()

        self._stamp_date_imported(graph, roots)
        return frozenset(subjects)

    def _stamp_date_imported(self, graph: Graph, subjects: Iterable[URIRef]) -> None:
        now = Literal(self._clock().astimezone(timezone.utc).replace(microsecond=0))
        for subject in subjects:
            graph.set((subject, SEOVOC_DATE_IMPORTED, now))

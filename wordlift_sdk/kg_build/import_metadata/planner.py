from __future__ import annotations

from rdflib import Graph, URIRef

from .hashing import compute_import_hash, set_import_hash, stored_import_hash
from .subjects import dataset_subjects, import_subjects
from .vocab import SEOVOC_IMPORT_HASH


class ImportWritePlanner:
    """Decide whether a graph is written, and stamp its import metadata.

    The one place both write strategies (``put`` and ``patch``) ask. With
    ``import_hash_mode`` ``on`` an unchanged graph is skipped; ``write`` stamps
    the hash without skipping; ``off`` leaves the hash out.
    """

    def plan(
        self, graph: Graph, dataset_uri: str, import_hash_mode: str = "on"
    ) -> frozenset[URIRef]:
        """Stamp import metadata on *graph*; return the subjects to write, if any."""
        subjects = dataset_subjects(graph, dataset_uri) if dataset_uri else set()
        if not subjects or import_hash_mode == "off":
            return frozenset(subjects)

        roots = import_subjects(graph, dataset_uri)
        representative = min(roots, key=str)
        stored = stored_import_hash(graph, representative)
        current = compute_import_hash(graph, representative, dataset_uri.rstrip("/"))
        for subject in subjects - roots:
            graph.remove((subject, SEOVOC_IMPORT_HASH, None))
        for subject in roots:
            set_import_hash(graph, subject, current)

        if import_hash_mode == "on" and stored == current:
            return frozenset()
        return frozenset(subjects)

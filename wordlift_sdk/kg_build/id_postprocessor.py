from __future__ import annotations

from rdflib import Graph

from .id_generator import CanonicalIdGenerator


class CanonicalIdsPostprocessor:
    """Postprocessor adapter that applies canonical ID generation to a graph."""

    def __init__(self, generator: CanonicalIdGenerator | None = None) -> None:
        self._generator = generator or CanonicalIdGenerator()

    def process_graph(self, graph: Graph, context) -> Graph:
        dataset_uri = str(getattr(context.account, "dataset_uri", "")).rstrip("/")
        if not dataset_uri:
            return graph
        return self._generator.apply(graph, dataset_uri)

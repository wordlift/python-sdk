from __future__ import annotations

from rdflib import Graph

from .id_generator import CanonicalIdGenerator
from .iri_lookup import IriLookup


class CanonicalIdsPostprocessor:
    """Postprocessor adapter that applies canonical ID generation to a graph."""

    def __init__(
        self,
        generator: CanonicalIdGenerator | None = None,
        iri_lookup: IriLookup | None = None,
        context_key: str = "kg_build.iri_lookup",
        strategy: str = "legacy",
    ) -> None:
        self._generator = generator or CanonicalIdGenerator(strategy=strategy)
        self._iri_lookup = iri_lookup
        self._context_key = context_key

    def process_graph(self, graph: Graph, context) -> Graph:
        dataset_uri = str(getattr(context.account, "dataset_uri", "")).rstrip("/")
        if not dataset_uri:
            return graph
        iri_lookup = self._iri_lookup or self._lookup_from_context(context)
        return self._generator.apply(graph, dataset_uri, iri_lookup=iri_lookup)

    def _lookup_from_context(self, context) -> IriLookup | None:
        extensions = getattr(context, "extensions", None)
        if not isinstance(extensions, dict):
            return None
        lookup = extensions.get(self._context_key)
        if lookup is None or not hasattr(lookup, "iri_for_subject"):
            return None
        return lookup

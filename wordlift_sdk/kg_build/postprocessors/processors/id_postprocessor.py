from __future__ import annotations

from rdflib import Graph, RDF, URIRef

from .id_generator import CanonicalIdGenerator
from ...iri_lookup import IriLookup


def _find_web_page_iri(graph: Graph) -> URIRef | None:
    for subject in graph.subjects(RDF.type, URIRef("http://schema.org/WebPage")):
        return subject
    for subject in graph.subjects(RDF.type, URIRef("https://schema.org/WebPage")):
        return subject
    return None


def _swap_iris(graph: Graph, old_iri: URIRef, new_iri: URIRef) -> None:
    for subject, predicate, obj in list(graph.triples((old_iri, None, None))):
        graph.remove((subject, predicate, obj))
        graph.add((new_iri, predicate, obj))
    for subject, predicate, obj in list(graph.triples((None, None, old_iri))):
        graph.remove((subject, predicate, obj))
        graph.add((subject, predicate, new_iri))


class RootIdReconcilerPostprocessor:
    """Rewrites the WebPage node IRI to match the existing web page ID.

    When a page has been imported before, the mapping may generate a different
    IRI than the one already stored. This postprocessor swaps all triples
    referencing the old IRI to use the canonical one from the system.
    Runs before custom postprocessors so they always see the correct subject.
    """

    def process_graph(self, graph: Graph, context) -> Graph:
        root_id = getattr(context, "existing_web_page_id", None)
        if not root_id:
            return graph
        old_iri = _find_web_page_iri(graph)
        if old_iri and str(old_iri) != root_id:
            _swap_iris(graph, old_iri, URIRef(root_id))
        return graph


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
        return self._generator.apply(
            graph,
            dataset_uri,
            iri_lookup=iri_lookup,
            language=getattr(context.account, "language", None),
        )

    def _lookup_from_context(self, context) -> IriLookup | None:
        extensions = getattr(context, "extensions", None)
        if not isinstance(extensions, dict):
            return None
        lookup = extensions.get(self._context_key)
        if lookup is None or not hasattr(lookup, "iri_for_subject"):
            return None
        return lookup

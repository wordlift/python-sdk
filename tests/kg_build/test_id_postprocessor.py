from __future__ import annotations

from types import SimpleNamespace

from rdflib import Graph, URIRef

from wordlift_sdk.kg_build.id_postprocessor import CanonicalIdsPostprocessor


def test_id_postprocessor_no_dataset_uri_returns_original_graph() -> None:
    graph = Graph()
    post = CanonicalIdsPostprocessor()
    context = SimpleNamespace(account=SimpleNamespace(dataset_uri=None))
    out = post.process_graph(graph, context)
    assert out is graph


def test_id_postprocessor_applies_generator_when_dataset_uri_present() -> None:
    graph = Graph()
    s = URIRef("https://example.com/a")
    graph.add((s, URIRef("https://example.com/p"), URIRef("https://example.com/o")))
    post = CanonicalIdsPostprocessor()
    context = SimpleNamespace(
        account=SimpleNamespace(dataset_uri="https://data.example.com/dataset")
    )
    out = post.process_graph(graph, context)
    assert isinstance(out, Graph)


def test_id_postprocessor_uses_lookup_from_context_extensions() -> None:
    graph = Graph()
    subject = URIRef("https://example.com/item")
    graph.add(
        (subject, URIRef("http://schema.org/url"), URIRef("https://example.com/item"))
    )

    class _Lookup:
        def iri_for_subject(self, graph, subject):
            return "https://kg.example.com/items/from-lookup"

    post = CanonicalIdsPostprocessor()
    context = SimpleNamespace(
        account=SimpleNamespace(dataset_uri="https://data.example.com/dataset"),
        extensions={"kg_build.iri_lookup": _Lookup()},
    )
    out = post.process_graph(graph, context)
    assert (
        URIRef("https://kg.example.com/items/from-lookup"),
        URIRef("http://schema.org/url"),
        URIRef("https://example.com/item"),
    ) in out

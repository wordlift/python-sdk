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

"""Lookup IRI ownership: the page root keeps its existing IRI (#62)."""

from __future__ import annotations

import pandas as pd
import pytest
from rdflib import RDF, Graph, Literal, URIRef

from wordlift_sdk.kg_build.iri_lookup import DataFrameUrlIriLookup
from wordlift_sdk.kg_build.postprocessors.processors.id_generator import (
    CanonicalIdGenerator,
)

SCHEMA = "http://schema.org/"
DATASET = "https://data.example.com"
PAGE_URL = "https://www.example.com/insurance/acme-review/"
EXISTING = URIRef(f"{DATASET}/articles/acme-review")
STRATEGIES = ["legacy", "dependency_graph"]


def _s(name: str) -> URIRef:
    return URIRef(f"{SCHEMA}{name}")


def _lookup() -> DataFrameUrlIriLookup:
    return DataFrameUrlIriLookup(
        pd.DataFrame([{"url": PAGE_URL, "iri": str(EXISTING)}])
    )


def _page(root_type: str) -> Graph:
    """Root <-> FAQPage cycle: every subject is linked to."""
    graph = Graph()
    root, faq = URIRef("urn:tmp:root"), URIRef("urn:tmp:faq")
    graph.add((root, RDF.type, _s(root_type)))
    graph.add((root, _s("name"), Literal("Acme review")))
    graph.add((root, _s("url"), Literal(PAGE_URL)))
    graph.add((root, _s("subjectOf"), faq))
    graph.add((faq, RDF.type, _s("FAQPage")))
    graph.add((faq, _s("about"), root))
    return graph


def _add_unlinked(graph: Graph, type_name: str, *, url: str | None = None) -> None:
    node = URIRef(f"urn:tmp:{type_name.lower()}")
    graph.add((node, RDF.type, _s(type_name)))
    graph.add((node, _s("name"), Literal(f"Stray {type_name}")))
    if url:
        graph.add((node, _s("url"), Literal(url)))


def _root(graph: Graph, root_type: str) -> URIRef:
    [root] = list(graph.subjects(_s("name"), Literal("Acme review")))
    assert (root, RDF.type, _s(root_type)) in graph
    return root


def _apply(graph: Graph, strategy: str) -> Graph:
    return CanonicalIdGenerator(strategy=strategy).apply(
        graph, DATASET, iri_lookup=_lookup()
    )


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("root_type", ["WebPage", "Review"])
def test_linked_root_keeps_iri_with_an_unlinked_node(strategy, root_type) -> None:
    graph = _page(root_type)
    _add_unlinked(graph, "VideoObject")

    output = _apply(graph, strategy)

    assert _root(output, root_type) == EXISTING
    [faq] = list(output.subjects(RDF.type, _s("FAQPage")))
    assert str(faq).startswith(f"{EXISTING}/")


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("root_type", ["WebPage", "Review"])
def test_unlinked_node_with_the_page_url_does_not_take_the_iri(
    strategy, root_type
) -> None:
    graph = _page(root_type)
    _add_unlinked(graph, "BreadcrumbList", url=PAGE_URL)

    output = _apply(graph, strategy)

    assert _root(output, root_type) == EXISTING
    [breadcrumb] = list(output.subjects(RDF.type, _s("BreadcrumbList")))
    assert breadcrumb != EXISTING


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_root_type_wins_over_a_more_linked_subject(strategy) -> None:
    graph = Graph()
    page, article = URIRef("urn:tmp:page"), URIRef("urn:tmp:article")
    graph.add((page, RDF.type, _s("WebPage")))
    graph.add((page, _s("url"), Literal(PAGE_URL)))
    graph.add((article, RDF.type, _s("Article")))
    graph.add((article, _s("url"), Literal(PAGE_URL)))
    graph.add((article, _s("name"), Literal("Acme")))
    graph.add((article, _s("headline"), Literal("Acme")))

    output = _apply(graph, strategy)

    assert (EXISTING, RDF.type, _s("WebPage")) in output
    assert (EXISTING, RDF.type, _s("Article")) not in output


def test_equally_ranked_subjects_resolve_to_the_smallest_iri() -> None:
    graph = Graph()
    for name in ("b", "a"):
        node = URIRef(f"urn:tmp:{name}")
        graph.add((node, RDF.type, _s("Article")))
        graph.add((node, _s("url"), Literal(PAGE_URL)))

    owners = CanonicalIdGenerator()._lookup_owners(graph, _lookup())

    assert owners == {URIRef("urn:tmp:a"): EXISTING}


def test_dependents_never_own_a_lookup_iri() -> None:
    graph = Graph()
    product, offer = URIRef("urn:tmp:product"), URIRef("urn:tmp:offer")
    graph.add((product, RDF.type, _s("Product")))
    graph.add((product, _s("offers"), offer))
    graph.add((offer, RDF.type, _s("Offer")))
    graph.add((offer, _s("url"), Literal(PAGE_URL)))

    assert CanonicalIdGenerator()._lookup_owners(graph, _lookup()) == {}


def test_no_lookup_means_no_owners() -> None:
    assert CanonicalIdGenerator()._lookup_owners(_page("WebPage"), None) == {}

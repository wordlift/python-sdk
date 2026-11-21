"""Lookup IRI ownership: the page root keeps its existing IRI (#62)."""

from __future__ import annotations

import re

import pandas as pd
import pytest
from rdflib import RDF, Graph, Literal, URIRef

from wordlift_sdk.kg_build.iri_lookup import DataFrameUrlIriLookup
from wordlift_sdk.kg_build.postprocessors.processors.id_generator import (
    CanonicalIdGenerator,
)
from wordlift_sdk.kg_build.postprocessors.processors.lookup_ownership import (
    resolve_lookup_ownership,
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
def test_other_node_with_the_page_url_is_nested_and_reported(
    strategy, root_type, caplog
) -> None:
    graph = _page(root_type)
    _add_unlinked(graph, "BreadcrumbList", url=PAGE_URL)

    output = _apply(graph, strategy)

    assert _root(output, root_type) == EXISTING
    [breadcrumb] = list(output.subjects(RDF.type, _s("BreadcrumbList")))
    assert breadcrumb == URIRef(f"{EXISTING}/breadcrumb-lists/breadcrumb-list")
    assert "2 subjects match lookup IRI" in caplog.text


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
    assert (URIRef(f"{EXISTING}/articles/article"), RDF.type, _s("Article")) in output


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_article_and_review_sharing_the_url_stay_put_across_syncs(strategy) -> None:
    """Re-syncing the output must not move any IRI (the URL keeps one entity)."""
    graph = _page("Review")
    _add_unlinked(graph, "Article", url=PAGE_URL)

    first = _apply(graph, strategy)
    first_subjects = set(first.subjects())
    second = _apply(Graph() + first, strategy)

    assert _root(first, "Review") == EXISTING
    assert URIRef(f"{EXISTING}/articles/article") in first_subjects
    assert set(second.subjects()) == first_subjects
    top_level = re.compile(rf"^{re.escape(DATASET)}/[^/]+/[^/]+$")
    url_owners = second.subjects(_s("url"), Literal(PAGE_URL))
    assert {s for s in url_owners if top_level.match(str(s))} == {EXISTING}


def test_equally_ranked_subjects_resolve_to_the_smallest_iri() -> None:
    graph = Graph()
    for name in ("b", "a"):
        node = URIRef(f"urn:tmp:{name}")
        graph.add((node, RDF.type, _s("Article")))
        graph.add((node, _s("url"), Literal(PAGE_URL)))

    ownership = resolve_lookup_ownership(
        graph, _lookup(), is_candidate=lambda s: True, rank=str
    )

    assert ownership.owners == {URIRef("urn:tmp:a"): EXISTING}
    assert ownership.losers == {URIRef("urn:tmp:b"): EXISTING}


def test_non_candidates_never_own_a_lookup_iri() -> None:
    graph = _page("WebPage")

    ownership = resolve_lookup_ownership(
        graph, _lookup(), is_candidate=lambda s: False, rank=str
    )

    assert ownership.owners == {} and ownership.losers == {}


def test_no_lookup_means_no_owners() -> None:
    ownership = resolve_lookup_ownership(
        _page("WebPage"), None, is_candidate=lambda s: True, rank=str
    )

    assert ownership.owners == {} and ownership.losers == {}

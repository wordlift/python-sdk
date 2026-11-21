"""Lookup IRI ownership: a linked page root keeps its existing IRI (#62)."""

from __future__ import annotations

import pandas as pd
import pytest
from rdflib import RDF, Graph, Literal, URIRef

from wordlift_sdk.kg_build.iri_lookup import DataFrameUrlIriLookup
from wordlift_sdk.kg_build.postprocessors.processors.id_generator import (
    CanonicalIdGenerator,
)
from wordlift_sdk.kg_build.postprocessors.processors.lookup_ownership import (
    resolve_lookup_owners,
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


def _page(root_type: str, root: URIRef = URIRef("urn:tmp:root")) -> Graph:
    """Root <-> FAQPage cycle: every subject is linked to."""
    graph = Graph()
    faq = URIRef("urn:tmp:faq")
    graph.add((root, RDF.type, _s(root_type)))
    graph.add((root, _s("name"), Literal("Acme review")))
    graph.add((root, _s("url"), Literal(PAGE_URL)))
    graph.add((root, _s("subjectOf"), faq))
    graph.add((faq, RDF.type, _s("FAQPage")))
    graph.add((faq, _s("about"), root))
    return graph


def _add(graph: Graph, name: str, type_name: str, *, url: str | None = None) -> URIRef:
    node = URIRef(f"urn:tmp:{name}")
    graph.add((node, RDF.type, _s(type_name)))
    graph.add((node, _s("name"), Literal(f"Acme {name}")))
    if url:
        graph.add((node, _s("url"), Literal(url)))
    return node


def _named(graph: Graph, name: str) -> URIRef:
    [subject] = list(graph.subjects(_s("name"), Literal(name)))
    return subject


def _apply(graph: Graph, strategy: str) -> Graph:
    return CanonicalIdGenerator(strategy=strategy).apply(
        graph, DATASET, iri_lookup=_lookup()
    )


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("root_type", ["WebPage", "Review"])
def test_linked_root_keeps_iri_with_an_unlinked_node(strategy, root_type) -> None:
    graph = _page(root_type)
    _add(graph, "video", "VideoObject")

    output = _apply(graph, strategy)

    assert _named(output, "Acme review") == EXISTING
    [faq] = list(output.subjects(RDF.type, _s("FAQPage")))
    assert str(faq).startswith(f"{EXISTING}/")


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_reimport_on_the_existing_iri_is_stable(strategy) -> None:
    """Re-import via ``__ID__``: the root already sits on the looked-up IRI."""
    graph = _page("Review", root=EXISTING)
    _add(graph, "video", "VideoObject")

    first = _apply(graph, strategy)
    second = _apply(Graph() + first, strategy)

    assert _named(first, "Acme review") == EXISTING
    assert set(second.subjects()) == set(first.subjects())


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_unlinked_match_keeps_the_iri_as_before_and_is_reported(
    strategy, caplog
) -> None:
    graph = _page("Review")
    _add(graph, "crumbs", "BreadcrumbList", url=PAGE_URL)

    output = _apply(graph, strategy)

    assert _named(output, "Acme crumbs") == EXISTING
    assert "2 subjects match lookup IRI" in caplog.text


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_webpage_with_a_main_entity_article_is_unchanged(strategy, caplog) -> None:
    graph = Graph()
    page = _add(graph, "page", "WebPage", url=PAGE_URL)
    article = _add(graph, "article", "Article", url=PAGE_URL)
    graph.add((page, _s("mainEntity"), article))

    output = _apply(graph, strategy)

    assert _named(output, "Acme page") == EXISTING
    article_iri = _named(output, "Acme article")
    assert str(article_iri).startswith(f"{DATASET}/articles/")
    assert article_iri != EXISTING
    assert "2 subjects match lookup IRI" in caplog.text


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_webpage_with_a_main_entity_product_keeps_gtin_identity(strategy) -> None:
    graph = Graph()
    page = _add(graph, "page", "WebPage", url=PAGE_URL)
    product = _add(graph, "product", "Product", url=PAGE_URL)
    offer = URIRef("urn:tmp:offer")
    graph.add((product, _s("gtin"), Literal("123")))
    graph.add((product, _s("offers"), offer))
    graph.add((offer, RDF.type, _s("Offer")))
    graph.add((page, _s("mainEntity"), product))

    output = _apply(graph, strategy)

    assert _named(output, "Acme page") == EXISTING
    product_iri = _named(output, "Acme product")
    assert product_iri == URIRef(f"{DATASET}/01/123")
    [offer_iri] = list(output.objects(product_iri, _s("offers")))
    assert str(offer_iri).startswith(f"{product_iri}/")


def _owners(graph: Graph, *, roots: set[URIRef]) -> dict[URIRef, URIRef]:
    generator = CanonicalIdGenerator()
    return resolve_lookup_owners(
        graph,
        _lookup(),
        roots=roots,
        is_candidate=lambda s: True,
        rank=lambda s, iri: generator._lookup_owner_rank(graph, s, iri),
    )


@pytest.mark.parametrize(
    ("types", "winner"),
    [
        ({"a": "Article", "b": "Review"}, "a"),
        ({"a": "Article", "b": "Product"}, "b"),
        ({"a": "Product", "b": "WebPage"}, "b"),
    ],
)
def test_without_matching_roots_the_best_ranked_match_wins(types, winner) -> None:
    graph = Graph()
    for name, type_name in types.items():
        _add(graph, name, type_name, url=PAGE_URL)

    owners = _owners(graph, roots=set())

    assert owners == {URIRef(f"urn:tmp:{winner}"): EXISTING}


def test_a_match_already_on_the_iri_wins() -> None:
    graph = Graph()
    _add(graph, "page", "WebPage", url=PAGE_URL)
    graph.add((EXISTING, RDF.type, _s("Article")))
    graph.add((EXISTING, _s("url"), Literal(PAGE_URL)))

    assert _owners(graph, roots=set()) == {EXISTING: EXISTING}


def test_every_matching_root_keeps_the_iri() -> None:
    graph = Graph()
    a = _add(graph, "a", "Article", url=PAGE_URL)
    b = _add(graph, "b", "Article", url=PAGE_URL)

    assert _owners(graph, roots={a, b}) == {a: EXISTING, b: EXISTING}


def test_non_candidates_and_missing_lookup_own_nothing() -> None:
    graph = _page("WebPage")
    no_candidates = resolve_lookup_owners(
        graph, _lookup(), roots=set(), is_candidate=lambda s: False, rank=str
    )
    no_lookup = resolve_lookup_owners(
        graph, None, roots=set(), is_candidate=lambda s: True, rank=str
    )

    assert no_candidates == {} and no_lookup == {}


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_fallback_never_merges_into_another_subject_on_the_iri(strategy) -> None:
    """Re-import: the Review sits on the IRI without the URL; the linked WebPage has it."""
    graph = Graph()
    graph.add((EXISTING, RDF.type, _s("Review")))
    graph.add((EXISTING, _s("name"), Literal("Acme review")))
    page = _add(graph, "page", "WebPage", url=PAGE_URL)
    graph.add((EXISTING, _s("mainEntityOfPage"), page))
    graph.add((page, _s("about"), EXISTING))
    _add(graph, "video", "VideoObject")

    output = _apply(graph, strategy)

    review, page_iri = _named(output, "Acme review"), _named(output, "Acme page")
    assert review != page_iri
    assert (review, RDF.type, _s("WebPage")) not in output
    assert (page_iri, RDF.type, _s("Review")) not in output


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_an_action_with_the_page_url_never_takes_the_iri(strategy) -> None:
    graph = _page("Article")
    action = _add(graph, "action", "Action", url=PAGE_URL)
    graph.add((URIRef("urn:tmp:root"), _s("potentialAction"), action))
    _add(graph, "video", "VideoObject")

    output = _apply(graph, strategy)

    article = _named(output, "Acme review")
    assert article == EXISTING
    assert str(_named(output, "Acme action")).startswith(f"{EXISTING}/actions/")

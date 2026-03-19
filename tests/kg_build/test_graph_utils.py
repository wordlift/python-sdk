from __future__ import annotations

from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.graph_utils import first_level_subjects

DATASET = "https://data.example.com"


def _uri(path: str) -> URIRef:
    return URIRef(f"{DATASET}/{path}")


def _ext(path: str) -> URIRef:
    return URIRef(f"https://external.example.com/{path}")


def test_empty_graph_returns_empty_set() -> None:
    assert first_level_subjects(Graph(), DATASET) == set()


def test_dataset_uri_match_returns_two_segment_subjects() -> None:
    g = Graph()
    canonical = _uri("articles/my-article")  # 2 segments → first-level
    deep = _uri("articles/my-article/comments/1")  # 4 segments → not first-level
    g.add((canonical, URIRef("https://schema.org/name"), Literal("Article")))
    g.add((deep, URIRef("https://schema.org/name"), Literal("Comment")))

    result = first_level_subjects(g, DATASET)
    assert canonical in result
    assert deep not in result


def test_dataset_uri_match_ignores_single_segment() -> None:
    g = Graph()
    one_seg = _uri("articles")  # 1 segment → not first-level by-id
    two_seg = _uri("articles/slug")  # 2 segments → first-level
    g.add((one_seg, URIRef("https://schema.org/name"), Literal("Collection")))
    g.add((two_seg, URIRef("https://schema.org/name"), Literal("Item")))

    result = first_level_subjects(g, DATASET)
    assert two_seg in result
    assert one_seg not in result


def test_fallback_to_unreferenced_subjects_when_no_dataset_match() -> None:
    g = Graph()
    root = _ext("root")
    child = _ext("child")
    # child is referenced by root, so root is the unreferenced subject
    g.add((root, URIRef("https://schema.org/hasPart"), child))
    g.add((child, URIRef("https://schema.org/name"), Literal("Child")))

    # No dataset_uri prefix match; fall back to "not referenced" logic
    result = first_level_subjects(g, "")
    assert root in result
    assert child not in result


def test_fallback_returns_all_when_everything_is_referenced() -> None:
    g = Graph()
    a = _ext("a")
    b = _ext("b")
    # mutual references: both are referenced
    g.add((a, URIRef("https://schema.org/hasPart"), b))
    g.add((b, URIRef("https://schema.org/hasPart"), a))

    result = first_level_subjects(g, "")
    assert result == {a, b}


def test_blank_dataset_uri_uses_reference_fallback() -> None:
    g = Graph()
    page = _ext("page")
    product = _ext("product")
    g.add((page, URIRef("https://schema.org/mentions"), product))
    g.add((product, URIRef("https://schema.org/name"), Literal("Product")))

    result = first_level_subjects(g, "")
    assert page in result
    assert product not in result


def test_dataset_uri_prefix_no_match_falls_back_gracefully() -> None:
    g = Graph()
    ext_subject = _ext("item")
    g.add((ext_subject, URIRef("https://schema.org/name"), Literal("External")))

    # dataset_uri set but no subject matches the prefix
    result = first_level_subjects(g, DATASET)
    assert ext_subject in result


def test_literal_objects_are_not_counted_as_subjects() -> None:
    g = Graph()
    s = _uri("things/item")
    g.add((s, URIRef("https://schema.org/name"), Literal("Name")))

    result = first_level_subjects(g, DATASET)
    assert s in result

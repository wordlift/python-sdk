from __future__ import annotations

from rdflib import Graph, Literal, RDF, URIRef

import wordlift_sdk.kg_build.id_allocator as id_allocator_module
from wordlift_sdk.kg_build.id_allocator import IdAllocator, normalize_slug


def _graph(subject: URIRef) -> Graph:
    g = Graph()
    g.add((subject, RDF.type, URIRef("http://schema.org/Thing")))
    g.add((subject, URIRef("http://schema.org/name"), Literal("Name Value")))
    return g


def test_normalize_slug_and_hash_fallback(monkeypatch) -> None:
    assert normalize_slug("  Hello__World!! ") == "hello-world"
    monkeypatch.setattr(
        id_allocator_module,
        "urlsplit",
        lambda _v: (_ for _ in ()).throw(RuntimeError("x")),
    )
    out = IdAllocator._url_hash("https://example.com?q=1")
    assert len(out) == 64


def test_assign_new_and_gtin_and_parent_paths() -> None:
    allocator = IdAllocator("https://data.example.com/dataset")
    g = Graph()
    created = allocator.assign(g, subject=None, type_name="Thing", base_value="Alpha")
    assert str(created).startswith("https://data.example.com/dataset/things/")

    s = URIRef("https://example.com/p")
    g.add((s, URIRef("http://schema.org/gtin"), Literal("ABC-123")))
    gtin_iri = allocator.assign(g, s)
    assert str(gtin_iri).startswith("https://data.example.com/dataset/01/")

    child = allocator.assign(
        g, subject=s, parent=URIRef("https://parent.example.com/root")
    )
    assert str(child).startswith("https://parent.example.com/root/things/")


def test_independent_child_new_helpers_and_force_index() -> None:
    allocator = IdAllocator("https://data.example.com/dataset")
    s = URIRef("https://example.com/s")
    g = _graph(s)
    iri = allocator.independent(g, s, rewrite=False, force_index=True, index=7)
    assert str(iri).endswith("-7")
    child = allocator.child(
        g, s, parent=URIRef("https://example.com/root"), rewrite=False
    )
    assert "/things/" in str(child)
    assert str(allocator.new_independent(g, type_name="Thing")).startswith(
        "https://data.example.com/dataset/things/"
    )
    assert str(
        allocator.new_child(g, parent=URIRef("https://example.com/root"))
    ).startswith("https://example.com/root/things/")


def test_entity_id_collision_and_subject_identity() -> None:
    allocator = IdAllocator("https://data.example.com/dataset")
    existing = URIRef("https://data.example.com/dataset/entities/name-value")
    g = _graph(existing)
    same = allocator._entity_id(
        g,
        existing,
        type_name="Thing",
        base_value="Name Value",
        index=None,
        force_index=False,
        url_value=None,
        path_prefix="https://data.example.com/dataset/entities/",
    )
    assert same == "name-value"

    other = URIRef("https://example.com/other")
    g.add((other, RDF.type, URIRef("http://schema.org/Thing")))
    g.add((other, URIRef("http://schema.org/name"), Literal("Name Value")))
    colliding = allocator._entity_id(
        g,
        other,
        type_name="Thing",
        base_value=None,
        index=None,
        force_index=False,
        url_value=None,
        path_prefix="https://data.example.com/dataset/entities/",
    )
    assert colliding.startswith("name-value-")


def test_swap_iri_and_helpers() -> None:
    old = URIRef("https://example.com/old")
    new = URIRef("https://example.com/new")
    ref = URIRef("https://example.com/ref")
    g = Graph()
    g.add((old, URIRef("http://schema.org/name"), Literal("A")))
    g.add((ref, URIRef("http://schema.org/about"), old))
    IdAllocator._swap_iri(g, old, new)
    assert (new, URIRef("http://schema.org/name"), Literal("A")) in g
    assert (ref, URIRef("http://schema.org/about"), new) in g

    assert IdAllocator._first_value(g, new, "name") == "A"
    assert IdAllocator._base_from_priority(g, new) == "A"

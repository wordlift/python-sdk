from __future__ import annotations

import hashlib

import pytest
from rdflib import Graph, Literal, RDF, URIRef

from wordlift_sdk.kg_build.postprocessors.processors.id_generator import (
    CanonicalIdGenerator,
)

SCHEMA = "http://schema.org/"
DATASET = "https://data.example.com"


def _entity(graph: Graph, key: str, name: str, type_name: str = "WebPage") -> URIRef:
    subject = URIRef(f"https://example.com/{key}")
    graph.add((subject, RDF.type, URIRef(f"{SCHEMA}{type_name}")))
    graph.add((subject, URIRef(f"{SCHEMA}name"), Literal(name)))
    return subject


@pytest.mark.parametrize("strategy", ["legacy", "dependency_graph"])
def test_non_latin_pages_remain_distinct_and_repeatable(strategy: str) -> None:
    graph = Graph()
    for key, name in (("a", "東京"), ("b", "北京")):
        _entity(graph, key, name)
    generator = CanonicalIdGenerator(strategy=strategy)
    generator.apply(graph, DATASET)
    subjects = set(graph.subjects(RDF.type, URIRef(f"{SCHEMA}WebPage")))
    assert len(subjects) == 2
    assert all(str(subject).isascii() for subject in subjects)
    assert len(graph) == 4
    before = set(graph)
    generator.apply(graph, DATASET)
    assert set(graph) == before


@pytest.mark.parametrize("strategy", ["legacy", "dependency_graph"])
@pytest.mark.parametrize("type_name", ["WebPage", "Product", "Person"])
def test_transliteration_collisions_stay_distinct_across_graphs(
    strategy: str, type_name: str
) -> None:
    generator = CanonicalIdGenerator(strategy=strategy)
    subjects = []
    for name in ("Müller", "Mueller"):
        graph = Graph()
        _entity(graph, "same-source", name, type_name)
        generator.apply(graph, DATASET, language="de")
        subjects.append(next(graph.subjects(RDF.type, URIRef(f"{SCHEMA}{type_name}"))))
    digest = hashlib.sha256("müller".encode()).hexdigest()
    assert str(subjects[0]).endswith(f"/mueller-{digest}")
    assert str(subjects[1]).endswith("/mueller")
    assert subjects[0] != subjects[1]


@pytest.mark.parametrize("strategy", ["legacy", "dependency_graph"])
def test_language_changes_do_not_leak_between_calls_and_keep_url_hash(
    strategy: str,
) -> None:
    generator = CanonicalIdGenerator(strategy=strategy)
    url = "https://example.com/page"
    digest = hashlib.sha256(url.encode()).hexdigest()
    for language, slug in (("de", "mueller"), ("tr", "muller"), ("de", "mueller")):
        graph = Graph()
        subject = _entity(graph, "a", "Müller")
        graph.add((subject, URIRef(f"{SCHEMA}url"), Literal(url)))
        generator.apply(graph, DATASET, language=language)
        assert URIRef(f"{DATASET}/web-pages/{slug}-{digest}") in set(graph.subjects())


@pytest.mark.parametrize("strategy", ["legacy", "dependency_graph"])
def test_lookup_iri_remains_authoritative(strategy: str) -> None:
    expected = URIRef(f"{DATASET}/web-pages/Müller")

    class Lookup:
        def iri_for_subject(self, graph: Graph, subject: URIRef) -> str:
            return str(expected)

    graph = Graph()
    _entity(graph, "a", "Müller")
    generator = CanonicalIdGenerator(strategy=strategy)
    generator.apply(graph, DATASET, iri_lookup=Lookup(), language="de")
    assert set(graph.subjects()) == {expected}


@pytest.mark.parametrize("strategy", ["legacy", "dependency_graph"])
def test_actions_and_questions_receive_language(strategy: str) -> None:
    graph = Graph()
    root = _entity(graph, "page", "Page")
    action = _entity(graph, "action", "Prüfen", "Action")
    faq = _entity(graph, "faq", "FAQ", "FAQPage")
    question = _entity(graph, "question", "Für wen", "Question")
    graph.add((root, URIRef(f"{SCHEMA}potentialAction"), action))
    graph.add((root, URIRef(f"{SCHEMA}hasPart"), faq))
    graph.add((faq, URIRef(f"{SCHEMA}mainEntity"), question))
    CanonicalIdGenerator(strategy=strategy).apply(graph, DATASET, language="de")
    for type_name, original, slug in (
        ("Action", "prüfen", "pruefen"),
        ("Question", "für wen", "fuer-wen"),
    ):
        subject = next(graph.subjects(RDF.type, URIRef(f"{SCHEMA}{type_name}")))
        digest = hashlib.sha256(original.encode()).hexdigest()
        assert str(subject).endswith(f"/{slug}-{digest}")


@pytest.mark.parametrize("strategy", ["legacy", "dependency_graph"])
@pytest.mark.parametrize("type_name", ["Question", "ImageObject", "VideoObject"])
@pytest.mark.parametrize("names", [("大阪", "東京"), ("大阪", "大阪", "大阪")])
def test_unicode_siblings_remain_distinct_and_idempotent(
    strategy: str, type_name: str, names: tuple[str, ...]
) -> None:
    graph = Graph()
    parent = _entity(graph, "page", "Page")
    predicate = {
        "Question": "mainEntity",
        "ImageObject": "image",
        "VideoObject": "video",
    }[type_name]
    if type_name == "Question":
        faq = _entity(graph, "faq", "FAQ", "FAQPage")
        graph.add((parent, URIRef(f"{SCHEMA}hasPart"), faq))
        parent = faq
    for key, name in zip(("a", "b", "c"), names):
        child = _entity(graph, key, name, type_name)
        graph.add((parent, URIRef(f"{SCHEMA}{predicate}"), child))
        graph.add((child, URIRef(f"{SCHEMA}description"), Literal(key)))
    generator = CanonicalIdGenerator(strategy=strategy)
    generator.apply(graph, DATASET, language="ja")
    assert len(set(graph.subjects(RDF.type, URIRef(f"{SCHEMA}{type_name}")))) == len(
        names
    )
    for key in ("a", "b", "c")[: len(names)]:
        assert (
            len(set(graph.subjects(URIRef(f"{SCHEMA}description"), Literal(key)))) == 1
        )
    first_pass = set(graph)
    generator.apply(graph, DATASET, language="ja")
    assert set(graph) == first_pass


def test_unicode_questions_linked_to_article_remain_idempotent() -> None:
    graph = Graph()
    article = _entity(graph, "article", "Article", "Article")
    faq = _entity(graph, "faq", "FAQ", "FAQPage")
    graph.add((article, URIRef(f"{SCHEMA}subjectOf"), faq))
    for key, name in (("a", "大阪"), ("b", "東京"), ("c", "大阪")):
        child = _entity(graph, key, name, "Question")
        graph.add((faq, URIRef(f"{SCHEMA}mainEntity"), child))
        graph.add((child, URIRef(f"{SCHEMA}description"), Literal(key)))
    generator = CanonicalIdGenerator()
    generator.apply(graph, DATASET, language="ja")
    assert len(set(graph.subjects(RDF.type, URIRef(f"{SCHEMA}Question")))) == 3
    first_pass = set(graph)
    generator.apply(graph, DATASET, language="ja")
    assert set(graph) == first_pass

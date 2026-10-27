from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from rdflib import XSD, Graph, Literal, URIRef

from wordlift_sdk.kg_build.import_metadata import (
    SEOVOC_DATE_IMPORTED,
    SEOVOC_IMPORT_HASH,
    ImportWritePlanner,
    compute_import_hash,
    import_subjects,
    set_import_hash,
    stored_import_hash,
)

DATASET = "https://data.example.com/dataset"
NAME = URIRef("https://schema.org/name")
PAGE = URIRef(f"{DATASET}/web-pages/1")
ARTICLE = URIRef(f"{DATASET}/articles/1")
CHILD = URIRef(f"{DATASET}/articles/1/faq/1")
EXTERNAL = URIRef("https://external.example.com/things/1")
NOW = datetime(2026, 10, 26, 14, 30, 45, 123456, tzinfo=timezone(timedelta(hours=2)))


def _graph() -> Graph:
    graph = Graph()
    graph.add((PAGE, URIRef("https://schema.org/mainEntity"), ARTICLE))
    graph.add((PAGE, NAME, Literal("Page")))
    graph.add((ARTICLE, URIRef("https://schema.org/hasPart"), CHILD))
    graph.add((CHILD, NAME, Literal("Child")))
    graph.add((EXTERNAL, NAME, Literal("External")))
    return graph


def _hashes(graph: Graph) -> dict[URIRef, str]:
    return {s: str(o) for s, o in graph.subject_objects(SEOVOC_IMPORT_HASH)}


def test_plan_stamps_one_hash_on_import_subjects_and_clears_children() -> None:
    graph = _graph()
    graph.add((CHILD, SEOVOC_IMPORT_HASH, Literal("stale")))

    subjects = ImportWritePlanner().plan(graph, f"{DATASET}/")

    assert subjects == {PAGE, ARTICLE, CHILD}
    expected = compute_import_hash(graph, PAGE, DATASET)
    assert _hashes(graph) == {PAGE: expected, ARTICLE: expected}


def test_plan_skips_unchanged_graph_only_in_on_mode() -> None:
    unchanged = _graph()
    stored = compute_import_hash(unchanged, PAGE, DATASET)

    for mode, expected in (("on", frozenset()), ("write", {PAGE, ARTICLE, CHILD})):
        graph = _graph()
        for root in (PAGE, ARTICLE):
            set_import_hash(graph, root, stored)
        assert ImportWritePlanner().plan(graph, DATASET, mode) == expected


def test_plan_off_mode_writes_everything_without_hash() -> None:
    graph = _graph()

    assert ImportWritePlanner().plan(graph, DATASET, "off") == {PAGE, ARTICLE, CHILD}
    assert _hashes(graph) == {}


@pytest.mark.parametrize("dataset_uri", ["", "https://other.example.com/x"])
def test_plan_has_nothing_to_write_outside_the_dataset(dataset_uri: str) -> None:
    assert ImportWritePlanner().plan(_graph(), dataset_uri) == frozenset()


def test_import_subjects_fall_back_to_unreferenced_dataset_subjects() -> None:
    root = URIRef(f"{DATASET}/a/b/c")
    leaf = URIRef(f"{DATASET}/a/b/c/d")
    graph = Graph()
    graph.add((root, URIRef("https://schema.org/hasPart"), leaf))
    graph.add((leaf, NAME, Literal("Leaf")))
    graph.add((EXTERNAL, NAME, Literal("External")))

    assert import_subjects(graph, DATASET) == {root}


def test_compute_import_hash_ignores_the_hash_and_outside_subjects() -> None:
    graph = _graph()
    before = compute_import_hash(graph, PAGE, DATASET)

    set_import_hash(graph, PAGE, "anything")
    graph.add((EXTERNAL, NAME, Literal("Changed")))

    assert compute_import_hash(graph, PAGE, DATASET) == before


def test_stored_import_hash_ignores_blank_values() -> None:
    graph = Graph()
    graph.add((PAGE, SEOVOC_IMPORT_HASH, Literal("  ")))

    assert stored_import_hash(graph, PAGE) is None
    set_import_hash(graph, PAGE, "h")
    assert stored_import_hash(graph, PAGE) == "h"


def test_compute_import_hash_covers_dataset_siblings() -> None:
    graph = _graph()
    before = compute_import_hash(graph, PAGE, DATASET)

    graph.set((CHILD, NAME, Literal("Changed child")))

    assert compute_import_hash(graph, PAGE, DATASET) != before


def _dates(graph: Graph) -> dict[URIRef, Literal]:
    return dict(graph.subject_objects(SEOVOC_DATE_IMPORTED))


@pytest.mark.parametrize("mode", ["on", "write", "off"])
def test_plan_stamps_utc_date_imported_on_import_subjects_when_writing(
    mode: str,
) -> None:
    graph = _graph()
    graph.add((PAGE, SEOVOC_DATE_IMPORTED, Literal(datetime(2020, 1, 1))))

    ImportWritePlanner(clock=lambda: NOW).plan(graph, DATASET, mode)

    stamp = Literal(datetime(2026, 10, 26, 12, 30, 45, tzinfo=timezone.utc))
    assert _dates(graph) == {PAGE: stamp, ARTICLE: stamp}
    assert stamp.datatype == XSD.dateTime


def test_plan_keeps_stored_date_when_skipping_unchanged_graph() -> None:
    graph = _graph()
    stored = compute_import_hash(graph, PAGE, DATASET)
    for root in (PAGE, ARTICLE):
        set_import_hash(graph, root, stored)

    assert ImportWritePlanner(clock=lambda: NOW).plan(graph, DATASET) == frozenset()
    assert _dates(graph) == {}


def test_compute_import_hash_ignores_date_imported() -> None:
    graph = _graph()
    before = compute_import_hash(graph, PAGE, DATASET)

    graph.add((PAGE, SEOVOC_DATE_IMPORTED, Literal(NOW)))

    assert compute_import_hash(graph, PAGE, DATASET) == before


def test_put_payload_carries_typed_date_imported() -> None:
    graph = _graph()
    ImportWritePlanner(clock=lambda: NOW).plan(graph, DATASET)

    turtle = graph.serialize(format="turtle")

    assert '"2026-10-26T12:30:45+00:00"^^xsd:dateTime' in turtle

from __future__ import annotations

import pandas as pd
from rdflib import Graph, Literal, URIRef

from wordlift_sdk.kg_build.iri_lookup import DataFrameUrlIriLookup

SCHEMA = "http://schema.org/"


def test_dataframe_url_iri_lookup_resolves_subject_url() -> None:
    lookup = DataFrameUrlIriLookup(
        pd.DataFrame(
            [
                {
                    "url": "https://example.com/path?a=2&b=1",
                    "iri": "https://kg.example.com/articles/example",
                }
            ]
        )
    )
    graph = Graph()
    subject = URIRef("urn:test")
    graph.add(
        (
            subject,
            URIRef(f"{SCHEMA}url"),
            Literal("https://EXAMPLE.com/path/?b=1&a=2#frag"),
        )
    )

    assert (
        lookup.iri_for_subject(graph, subject)
        == "https://kg.example.com/articles/example"
    )


def test_dataframe_url_iri_lookup_returns_none_when_not_found() -> None:
    lookup = DataFrameUrlIriLookup(
        pd.DataFrame([{"url": "https://example.com/a", "iri": "https://kg/x"}])
    )
    graph = Graph()
    subject = URIRef("urn:test")
    graph.add((subject, URIRef(f"{SCHEMA}url"), Literal("https://example.com/b")))

    assert lookup.iri_for_subject(graph, subject) is None


def test_dataframe_url_iri_lookup_duplicate_uses_shortest_path_parent() -> None:
    lookup = DataFrameUrlIriLookup(
        pd.DataFrame(
            [
                {
                    "url": "https://example.com/article",
                    "iri": "https://kg.example.com/articles/article/actions/action-1",
                },
                {
                    "url": "https://example.com/article",
                    "iri": "https://kg.example.com/articles/article",
                },
            ]
        )
    )
    graph = Graph()
    subject = URIRef("urn:test")
    graph.add((subject, URIRef(f"{SCHEMA}url"), Literal("https://example.com/article")))

    assert (
        lookup.iri_for_subject(graph, subject)
        == "https://kg.example.com/articles/article"
    )

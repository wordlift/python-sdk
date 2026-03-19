from __future__ import annotations

from rdflib import Graph, URIRef


def first_level_subjects(graph: Graph, dataset_uri: str) -> set[URIRef]:
    """Return the first-level URIRef subjects of *graph*.

    When *dataset_uri* is set, first-level subjects are those whose IRI matches
    ``<dataset_uri>/<type>/<id>`` (exactly two non-empty path segments after the
    base URI).  Falls back to subjects that are not referenced as objects by any
    other triple; if every subject is referenced, returns all subjects.
    """
    subjects = {s for s in graph.subjects() if isinstance(s, URIRef)}
    if dataset_uri:
        first_level_by_id = {
            s
            for s in subjects
            if str(s).startswith(f"{dataset_uri}/")
            and len([p for p in str(s)[len(dataset_uri) + 1 :].split("/") if p]) == 2
        }
        if first_level_by_id:
            return first_level_by_id

    referenced = {
        obj
        for _, _, obj in graph.triples((None, None, None))
        if isinstance(obj, URIRef) and obj in subjects
    }
    first_level = subjects - referenced
    return first_level or subjects

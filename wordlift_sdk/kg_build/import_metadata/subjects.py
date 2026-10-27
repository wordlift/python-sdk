from __future__ import annotations

from rdflib import Graph, URIRef

from ..graph_utils import first_level_subjects


def dataset_subjects(graph: Graph, dataset_uri: str) -> set[URIRef]:
    """Return the URIRef subjects of *graph* that live in the dataset."""
    base = dataset_uri.rstrip("/")
    return {
        subject
        for subject in graph.subjects()
        if isinstance(subject, URIRef) and str(subject).startswith(f"{base}/")
    }


def import_subjects(graph: Graph, dataset_uri: str) -> set[URIRef]:
    """Return the first-level dataset subjects that carry a graph's import metadata."""
    base = dataset_uri.rstrip("/")
    return first_level_subjects(graph, base, dataset_subjects(graph, base))

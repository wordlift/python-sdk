from __future__ import annotations

import hashlib

from rdflib import Graph, Literal, URIRef

from .vocab import SEOVOC_IMPORT_HASH


def compute_import_hash(graph: Graph, iri: URIRef, dataset_uri: str = "") -> str:
    """Hash the triples of *iri* and its dataset siblings, without the hash itself."""
    siblings = {
        subject
        for subject in graph.subjects()
        if isinstance(subject, URIRef)
        and (not dataset_uri or str(subject).startswith(dataset_uri))
    }
    siblings.add(iri)
    terms = sorted(
        f"{subject.n3()} {predicate.n3()} {obj.n3()}"
        for subject in siblings
        for _, predicate, obj in graph.triples((subject, None, None))
        if predicate != SEOVOC_IMPORT_HASH
    )
    return hashlib.sha256("\n".join(terms).encode("utf-8")).hexdigest()


def stored_import_hash(graph: Graph, iri: URIRef) -> str | None:
    """Return the import hash *graph* already carries for *iri*, if any."""
    for obj in graph.objects(iri, SEOVOC_IMPORT_HASH):
        if value := str(obj).strip():
            return value
    return None


def set_import_hash(graph: Graph, iri: URIRef, import_hash: str) -> None:
    graph.set((iri, SEOVOC_IMPORT_HASH, Literal(import_hash)))

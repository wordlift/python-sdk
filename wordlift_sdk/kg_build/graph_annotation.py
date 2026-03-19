from __future__ import annotations

from rdflib import Graph, Literal, URIRef

SEOVOC_SOURCE = URIRef("https://w3id.org/seovoc/source")
SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")


def _first_level_subjects(graph: Graph, dataset_uri: str) -> set[URIRef]:
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


class ImportAnnotationPostprocessor:
    """Stamps first-level graph subjects with web-page-import provenance metadata.

    Sets seovoc:source to 'web-page-import' on every first-level subject, and
    optionally propagates the existing import hash to all URIRef subjects when
    import_hash_mode is not 'off'. Both are needed before graph persistence so
    the KG can track provenance and skip unchanged imports.

    Reads from context:
      - account.dataset_uri  — for first-level subject resolution
      - existing_import_hash — hash from a prior import of the same page
      - import_hash_mode     — 'on' | 'write' | 'off'
    """

    def process_graph(self, graph: Graph, context) -> Graph:
        dataset_uri = str(
            getattr(getattr(context, "account", None), "dataset_uri", "") or ""
        ).rstrip("/")
        for subject in _first_level_subjects(graph, dataset_uri):
            graph.set((subject, SEOVOC_SOURCE, Literal("web-page-import")))

        import_hash_mode = getattr(context, "import_hash_mode", "on")
        if import_hash_mode == "off":
            return graph
        existing_import_hash = getattr(context, "existing_import_hash", None)
        if not existing_import_hash:
            return graph
        for subject in (s for s in graph.subjects() if isinstance(s, URIRef)):
            graph.set((subject, SEOVOC_IMPORT_HASH, Literal(existing_import_hash)))

        return graph

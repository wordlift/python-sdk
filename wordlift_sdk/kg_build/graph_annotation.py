from __future__ import annotations

from rdflib import Graph, Literal, URIRef

from .graph_utils import first_level_subjects

SEOVOC_SOURCE = URIRef("https://w3id.org/seovoc/source")
SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")


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
        for subject in first_level_subjects(graph, dataset_uri):
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

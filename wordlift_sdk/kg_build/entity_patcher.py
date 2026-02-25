from __future__ import annotations

import hashlib

from rdflib import Graph, Literal, URIRef
from wordlift_client.models.entity_patch_request import EntityPatchRequest
from wordlift_sdk.protocol import Context
from wordlift_sdk.protocol.entity_patch import EntityPatch

SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")


class EntityPatcher:
    """Queue entity patches from an RDFLib graph."""

    def __init__(self, context: Context) -> None:
        self._context = context

    async def patch(
        self, iri: URIRef, graph: Graph, import_hash_mode: str = "on"
    ) -> None:
        dataset_uri = str(
            getattr(self._context.account, "dataset_uri", "") or ""
        ).rstrip("/")
        non_hash_predicates = {
            predicate
            for _, predicate, _ in graph.triples((iri, None, None))
            if predicate != SEOVOC_IMPORT_HASH
        }
        if not non_hash_predicates:
            return

        if import_hash_mode != "off":
            existing_hash = self._existing_import_hash(iri, graph)
            import_hash = self._compute_import_hash(iri, graph, dataset_uri)
            self._set_import_hash(iri, graph, import_hash)
            if (
                import_hash_mode == "on"
                and existing_hash
                and existing_hash == import_hash
            ):
                return

        predicates = {predicate for _, predicate, _ in graph.triples((iri, None, None))}
        if not predicates:
            return

        patches: list[EntityPatchRequest] = []
        for predicate in predicates:
            path = f"/{predicate}"

            mini_graph = Graph()
            for _, _, obj in graph.triples((iri, predicate, None)):
                mini_graph.add((iri, predicate, obj))

            json_ld = mini_graph.serialize(format="json-ld", auto_compact=True)
            patches.append(EntityPatchRequest(op="remove", path=path))
            patches.append(EntityPatchRequest(op="add", path=path, value=json_ld))

        await self._context.entity_patch_queue.put(EntityPatch(iri, patches))

    async def patch_all(self, graph: Graph, import_hash_mode: str = "on") -> None:
        dataset_uri = getattr(self._context.account, "dataset_uri", None)
        if not dataset_uri:
            return

        subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(dataset_uri)
        }

        for iri in subjects:
            await self.patch(iri, graph, import_hash_mode=import_hash_mode)

    @staticmethod
    def _existing_import_hash(iri: URIRef, graph: Graph) -> str | None:
        for obj in graph.objects(iri, SEOVOC_IMPORT_HASH):
            value = str(obj).strip()
            if value:
                return value
        return None

    @staticmethod
    def _set_import_hash(iri: URIRef, graph: Graph, import_hash: str) -> None:
        graph.remove((iri, SEOVOC_IMPORT_HASH, None))
        graph.add((iri, SEOVOC_IMPORT_HASH, Literal(import_hash)))

    @staticmethod
    def _compute_import_hash(iri: URIRef, graph: Graph, dataset_uri: str = "") -> str:
        sibling_subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef)
            and (not dataset_uri or str(subject).startswith(dataset_uri))
        }
        sibling_subjects.add(iri)

        terms: list[str] = []
        for subject in sibling_subjects:
            for _, predicate, obj in graph.triples((subject, None, None)):
                if predicate == SEOVOC_IMPORT_HASH:
                    continue
                terms.append(f"{subject.n3()} {predicate.n3()} {obj.n3()}")
        digest_input = "\n".join(sorted(terms))
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

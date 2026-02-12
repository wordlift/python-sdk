from __future__ import annotations

from rdflib import Graph, URIRef
from wordlift_client.models.entity_patch_request import EntityPatchRequest
from wordlift_sdk.protocol import Context
from wordlift_sdk.protocol.entity_patch import EntityPatch


class EntityPatcher:
    """Queue entity patches from an RDFLib graph."""

    def __init__(self, context: Context) -> None:
        self._context = context

    async def patch(self, iri: URIRef, graph: Graph) -> None:
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

    async def patch_all(self, graph: Graph) -> None:
        dataset_uri = getattr(self._context.account, "dataset_uri", None)
        if not dataset_uri:
            return

        subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(dataset_uri)
        }

        for iri in subjects:
            subgraph = Graph()
            for _, predicate, obj in graph.triples((iri, None, None)):
                subgraph.add((iri, predicate, obj))
            await self.patch(iri, subgraph)

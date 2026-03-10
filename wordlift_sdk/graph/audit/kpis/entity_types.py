"""KPI: entity count by RDF type."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rdflib import Graph, RDF, URIRef


@dataclass(frozen=True)
class EntityTypesResult:
    by_type: dict[str, int]

    def to_dict(self) -> dict:
        return {"entity_types": self.by_type}


class EntityTypesKpi:
    """Count distinct entity IRIs grouped by rdf:type."""

    def collect(self, graph: Graph) -> EntityTypesResult:
        buckets: defaultdict[str, set[str]] = defaultdict(set)
        for s, _, o in graph.triples((None, RDF.type, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                buckets[str(o)].add(str(s))
        by_type = {t: len(iris) for t, iris in sorted(buckets.items())}
        return EntityTypesResult(by_type=by_type)


__all__ = ["EntityTypesKpi", "EntityTypesResult"]

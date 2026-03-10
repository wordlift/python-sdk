"""KPI: total entity, property, and triple counts."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, RDF, URIRef


@dataclass(frozen=True)
class TotalsResult:
    total_entities: int
    total_properties: int
    total_triples: int

    def to_dict(self) -> dict:
        return {
            "total_entities": self.total_entities,
            "total_properties": self.total_properties,
            "total_triples": self.total_triples,
        }


class TotalsKpi:
    """Aggregate triple-level counts for the whole graph."""

    def collect(self, graph: Graph) -> TotalsResult:
        entities: set[str] = set()
        properties = 0
        for s, p, _ in graph:
            if isinstance(s, URIRef):
                entities.add(str(s))
            if p != RDF.type and isinstance(p, URIRef):
                properties += 1
        return TotalsResult(
            total_entities=len(entities),
            total_properties=properties,
            total_triples=len(graph),
        )


__all__ = ["TotalsKpi", "TotalsResult"]

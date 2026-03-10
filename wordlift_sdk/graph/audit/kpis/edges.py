"""KPI: edge count (object-property triples)."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, URIRef


@dataclass(frozen=True)
class EdgesResult:
    count: int

    def to_dict(self) -> dict:
        return {"edges": self.count}


class EdgesKpi:
    """Count triples whose object is a URIRef (object properties, not data properties)."""

    def collect(self, graph: Graph) -> EdgesResult:
        count = sum(1 for _, _, o in graph if isinstance(o, URIRef))
        return EdgesResult(count=count)


__all__ = ["EdgesKpi", "EdgesResult"]

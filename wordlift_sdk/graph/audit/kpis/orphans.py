"""KPI: orphan entities (subjects with no incoming edges)."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, URIRef


@dataclass(frozen=True)
class OrphansResult:
    count: int
    iris: list[str]

    def to_dict(self) -> dict:
        return {"orphans": {"count": self.count, "iris": self.iris}}


class OrphansKpi:
    """Find subject IRIs that never appear as an object in any triple."""

    def collect(self, graph: Graph) -> OrphansResult:
        subjects = {str(s) for s in graph.subjects() if isinstance(s, URIRef)}
        objects = {str(o) for o in graph.objects() if isinstance(o, URIRef)}
        orphans = sorted(subjects - objects)
        return OrphansResult(count=len(orphans), iris=orphans)


__all__ = ["OrphansKpi", "OrphansResult"]

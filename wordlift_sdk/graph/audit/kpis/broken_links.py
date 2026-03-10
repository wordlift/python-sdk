"""KPI: broken links (object IRIs with no outgoing triples)."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, RDF, URIRef


@dataclass(frozen=True)
class BrokenLinksResult:
    count: int
    iris: list[str]

    def to_dict(self) -> dict:
        return {"broken_links": {"count": self.count, "iris": self.iris}}


class BrokenLinksKpi:
    """Find object IRIs that never appear as a subject (dangling references)."""

    def collect(self, graph: Graph) -> BrokenLinksResult:
        subjects = {str(s) for s in graph.subjects() if isinstance(s, URIRef)}
        # Only consider object IRIs from non-rdf:type triples (relationship edges)
        object_iris = {
            str(o) for s, p, o in graph if p != RDF.type and isinstance(o, URIRef)
        }
        broken = sorted(object_iris - subjects)
        return BrokenLinksResult(count=len(broken), iris=broken)


__all__ = ["BrokenLinksKpi", "BrokenLinksResult"]

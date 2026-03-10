"""KPI: property assertion count by predicate."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from rdflib import Graph, RDF, URIRef


@dataclass(frozen=True)
class PropertiesResult:
    by_predicate: dict[str, int]

    def to_dict(self) -> dict:
        return {"properties": self.by_predicate}


class PropertiesKpi:
    """Count property assertions (excluding rdf:type) grouped by predicate IRI."""

    def collect(self, graph: Graph) -> PropertiesResult:
        counter: Counter[str] = Counter()
        for _, p, _ in graph:
            if p != RDF.type and isinstance(p, URIRef):
                counter[str(p)] += 1
        by_predicate = dict(sorted(counter.items()))
        return PropertiesResult(by_predicate=by_predicate)


__all__ = ["PropertiesKpi", "PropertiesResult"]

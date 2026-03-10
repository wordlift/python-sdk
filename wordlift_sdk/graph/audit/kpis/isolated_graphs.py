"""KPI: isolated (disconnected) graph components."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rdflib import Graph, URIRef


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def components(self) -> list[list[str]]:
        buckets: defaultdict[str, list[str]] = defaultdict(list)
        for node in self._parent:
            buckets[self.find(node)].append(node)
        return [sorted(members) for members in buckets.values()]


@dataclass(frozen=True)
class IsolatedGraphsResult:
    component_count: int
    components: list[list[str]] | None

    def to_dict(self) -> dict:
        result: dict = {"isolated_graphs": {"component_count": self.component_count}}
        if self.components is not None:
            result["isolated_graphs"]["components"] = self.components
        return result


class IsolatedGraphsKpi:
    """Find disconnected components using union-find on IRI nodes."""

    def __init__(self, list_components: bool = False) -> None:
        self._list_components = list_components

    def collect(self, graph: Graph) -> IsolatedGraphsResult:
        # Only entity IRIs that appear as subjects are graph nodes
        entity_iris = {str(s) for s in graph.subjects() if isinstance(s, URIRef)}
        uf = _UnionFind()
        for iri in entity_iris:
            uf.find(iri)  # register every entity
        # Union entities connected by relationship edges (both ends must be entities)
        for s, _, o in graph:
            if (
                isinstance(s, URIRef)
                and isinstance(o, URIRef)
                and str(s) in entity_iris
                and str(o) in entity_iris
            ):
                uf.union(str(s), str(o))
        components = uf.components()
        return IsolatedGraphsResult(
            component_count=len(components),
            components=components if self._list_components else None,
        )


__all__ = ["IsolatedGraphsKpi", "IsolatedGraphsResult"]

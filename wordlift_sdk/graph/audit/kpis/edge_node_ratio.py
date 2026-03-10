"""KPI: edge-to-node ratio (graph density)."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, URIRef


@dataclass(frozen=True)
class EdgeNodeRatioResult:
    ratio: float
    edges: int
    nodes: int

    def to_dict(self) -> dict:
        return {
            "edge_node_ratio": {
                "ratio": self.ratio,
                "edges": self.edges,
                "nodes": self.nodes,
            }
        }


class EdgeNodeRatioKpi:
    """Compute edge-to-node ratio: object-property triples / distinct subject IRIs."""

    def collect(self, graph: Graph) -> EdgeNodeRatioResult:
        nodes = {str(s) for s in graph.subjects() if isinstance(s, URIRef)}
        edges = sum(1 for _, _, o in graph if isinstance(o, URIRef))
        node_count = len(nodes)
        ratio = edges / node_count if node_count else 0.0
        return EdgeNodeRatioResult(ratio=round(ratio, 4), edges=edges, nodes=node_count)


__all__ = ["EdgeNodeRatioKpi", "EdgeNodeRatioResult"]

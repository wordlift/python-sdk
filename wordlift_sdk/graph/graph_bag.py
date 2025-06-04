from dataclasses import dataclass
from rdflib import Graph


@dataclass
class GraphBag:
    graph: Graph

import hashlib
from queue import Queue
from typing import Optional

from rdflib import Graph
from rdflib.compare import to_isomorphic


class GraphQueue:
    queue: Queue[Graph]
    hashes: set[str]

    def __init__(self):
        self.queue = Queue()
        self.hashes = set()

    def put(self, graph: Graph) -> None:
        hash = GraphQueue.hash_graph(graph)
        if hash not in self.hashes:
            self.queue.put(graph)
            self.hashes.add(hash)

    def get(self) -> Optional[Graph]:
        if not self.queue.empty():
            graph = self.queue.get()
            hash = GraphQueue.hash_graph(graph)
            self.hashes.remove(hash)
            return graph

        return None

    def __len__(self) -> int:
        return self.queue.qsize()

    @staticmethod
    def hash_graph(graph: Graph) -> str:
        iso = to_isomorphic(graph)
        canon = iso.serialize(format="nt")
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

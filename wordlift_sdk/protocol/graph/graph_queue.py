import hashlib

import wordlift_client
from rdflib import Graph
from rdflib.compare import to_isomorphic
from wordlift_client import Configuration


class GraphQueue:
    client_configuration: Configuration
    hashes: set[str]

    def __init__(self, client_configuration: Configuration):
        self.client_configuration = client_configuration
        self.hashes = set()

    async def put(self, graph: Graph) -> None:
        hash = GraphQueue.hash_graph(graph)
        if hash not in self.hashes:
            self.hashes.add(hash)

            async with wordlift_client.ApiClient(
                configuration=self.client_configuration
            ) as api_client:
                api_instance = wordlift_client.EntitiesApi(api_client)
                await api_instance.create_or_update_entities(
                    graph.serialize(format="turtle"),
                    _content_type="text/turtle",
                )

    @staticmethod
    def hash_graph(graph: Graph) -> str:
        iso = to_isomorphic(graph)
        canon = iso.serialize(format="nt")
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

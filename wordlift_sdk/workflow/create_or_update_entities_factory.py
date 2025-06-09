from wordlift_client import Configuration
from rdflib import Graph
import wordlift_client


async def create_or_update_entities_factory(configuration: Configuration):
    async def callback(graph: Graph):
        # Run all the queued graphs.
        async with wordlift_client.ApiClient(configuration=configuration) as api_client:
            api_instance = wordlift_client.EntitiesApi(api_client)
            await api_instance.create_or_update_entities(
                graph.serialize(format="turtle"),
                _content_type="text/turtle",
            )

    return callback

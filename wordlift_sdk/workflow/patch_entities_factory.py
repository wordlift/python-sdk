import wordlift_client
from wordlift_client import Configuration

from ..protocol.entity_patch import EntityPatch


async def patch_entities_factory(configuration: Configuration):
    async def callback(entity_patch: EntityPatch):
        # Run all the queued graphs.
        async with wordlift_client.ApiClient(configuration=configuration) as api_client:
            api_instance = wordlift_client.EntitiesApi(api_client)
            await api_instance.patch_entities(
                id=entity_patch.iri, entity=entity_patch.requests
            )

    return callback

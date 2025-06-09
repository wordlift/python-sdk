import wordlift_client
from wordlift_client import Configuration

from .entity_patch import EntityPatch


class EntityPatchQueue:
    client_configuration: Configuration

    def __init__(self, client_configuration: Configuration):
        self.client_configuration = client_configuration

    async def put(self, entity_patch: EntityPatch) -> None:
        async with wordlift_client.ApiClient(
            configuration=self.client_configuration
        ) as api_client:
            api_instance = wordlift_client.EntitiesApi(api_client)
            await api_instance.patch_entities(
                id=entity_patch.iri, entity=entity_patch.requests
            )

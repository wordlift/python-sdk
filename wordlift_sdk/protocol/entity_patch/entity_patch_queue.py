import logging
import wordlift_client
from wordlift_client import Configuration

from .entity_patch import EntityPatch
from ..write_retry import retry_write

logger = logging.getLogger(__name__)


class EntityPatchQueue:
    client_configuration: Configuration

    def __init__(self, client_configuration: Configuration):
        self.client_configuration = client_configuration

    @retry_write(logger)
    async def put(self, entity_patch: EntityPatch) -> None:
        async with wordlift_client.ApiClient(
            configuration=self.client_configuration
        ) as api_client:
            api_instance = wordlift_client.EntitiesApi(api_client)

            try:
                await api_instance.patch_entities(
                    id=entity_patch.iri, entity_patch_request=entity_patch.requests
                )
            except Exception as e:
                logger.error("Error patching entities", exc_info=e)
                raise e

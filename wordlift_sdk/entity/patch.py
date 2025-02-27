from typing import List, Optional

import wordlift_client
from wordlift_client import Configuration, EntityPatchRequest


async def patch(configuration: Configuration, entity_id: str, payloads: List[EntityPatchRequest]) -> Optional[str]:
    # If the payloads are empty, exit.
    if not payloads:
        return None

    async with wordlift_client.ApiClient(configuration) as api_client:
        api_instance = wordlift_client.EntitiesApi(api_client)
        return await api_instance.patch_entities(entity_id, payloads)

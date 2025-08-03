import logging
import asyncio
import aiohttp
import pydantic_core
import wordlift_client
from wordlift_client import Configuration

from .entity_patch import EntityPatch
from tenacity import retry, retry_if_exception_type, wait_fixed, after_log

logger = logging.getLogger(__name__)


class EntityPatchQueue:
    client_configuration: Configuration

    def __init__(self, client_configuration: Configuration):
        self.client_configuration = client_configuration

    @retry(
        # stop=stop_after_attempt(5),  # Retry up to 5 times
        retry=retry_if_exception_type(
            asyncio.TimeoutError
            | aiohttp.client_exceptions.ServerDisconnectedError
            | aiohttp.client_exceptions.ClientConnectorError
            | aiohttp.client_exceptions.ClientPayloadError
            | aiohttp.client_exceptions.ClientConnectorDNSError
            | pydantic_core._pydantic_core.ValidationError
            | wordlift_client.exceptions.ServiceException
            | wordlift_client.exceptions.BadRequestException
            | aiohttp.client_exceptions.ClientOSError
        ),
        wait=wait_fixed(2),  # Wait 2 seconds between retries
        after=after_log(logger, logging.WARNING),
        reraise=True,
    )
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

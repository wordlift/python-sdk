import hashlib
import logging
import aiohttp
import asyncio

import pydantic_core
import wordlift_client
from rdflib import Graph
from rdflib.compare import to_isomorphic
from wordlift_client import Configuration
from tenacity import retry, retry_if_exception_type, wait_fixed, after_log

logger = logging.getLogger(__name__)


class GraphQueue:
    client_configuration: Configuration
    hashes: set[str]

    def __init__(self, client_configuration: Configuration):
        self.client_configuration = client_configuration
        self.hashes = set()

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
    async def put(self, graph: Graph) -> None:
        hash = GraphQueue.hash_graph(graph)
        if hash not in self.hashes:
            self.hashes.add(hash)

            async with wordlift_client.ApiClient(
                configuration=self.client_configuration
            ) as api_client:
                api_instance = wordlift_client.EntitiesApi(api_client)

                try:
                    await api_instance.create_or_update_entities(
                        graph.serialize(format="turtle"),
                        _content_type="text/turtle",
                    )
                except Exception as e:
                    logger.error(f"Failed to create entities: {e}", exc_info=e)
                    raise e

    @staticmethod
    def hash_graph(graph: Graph) -> str:
        iso = to_isomorphic(graph)
        canon = iso.serialize(format="nt")
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

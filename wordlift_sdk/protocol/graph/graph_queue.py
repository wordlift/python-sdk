import hashlib
import logging
import asyncio

import wordlift_client
from rdflib import Graph
from rdflib.compare import to_isomorphic
from wordlift_client import Configuration

from ..write_retry import retry_write

logger = logging.getLogger(__name__)


class GraphQueue:
    client_configuration: Configuration
    hashes: set[str]

    def __init__(self, client_configuration: Configuration):
        self.client_configuration = client_configuration
        self.hashes = set()
        self._api_client: wordlift_client.ApiClient | None = None
        self._api_client_lock: asyncio.Lock | None = None

    async def _get_api_client(self) -> wordlift_client.ApiClient:
        # Lazy-init the lock (must be created on the event loop).
        if self._api_client_lock is None:
            self._api_client_lock = asyncio.Lock()
        if self._api_client is not None:
            return self._api_client
        async with self._api_client_lock:
            if self._api_client is None:
                # ApiClient.__init__ calls ssl.create_default_context() synchronously
                # and must run on the event loop thread (it calls asyncio internals).
                # Creating it once and caching avoids repeated SSL cert loading per put().
                client = wordlift_client.ApiClient(
                    configuration=self.client_configuration
                )
                await client.__aenter__()
                self._api_client = client
        return self._api_client

    async def close(self) -> None:
        if self._api_client is not None:
            try:
                await self._api_client.__aexit__(None, None, None)
            except Exception:
                pass
            self._api_client = None

    @retry_write(logger)
    async def put(self, graph: Graph) -> None:
        loop = asyncio.get_event_loop()
        hash = await loop.run_in_executor(None, GraphQueue.hash_graph, graph)
        if hash in self.hashes:
            return

        api_client = await self._get_api_client()
        api_instance = wordlift_client.EntitiesApi(api_client)

        try:
            await api_instance.create_or_update_entities(
                graph.serialize(format="turtle"),
                _content_type="text/turtle",
            )
        except Exception as e:
            logger.error(f"Failed to create entities: {e}", exc_info=e)
            raise e

        # Record the hash only after a successful write, so a retry after a
        # failed PUT sends the graph again instead of skipping it.
        self.hashes.add(hash)

    @staticmethod
    def hash_graph(graph: Graph) -> str:
        iso = to_isomorphic(graph)
        canon = iso.serialize(format="nt")
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

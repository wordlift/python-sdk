import asyncio
import logging
from os import cpu_count

import aiohttp
from tenacity import retry, retry_if_exception_type, wait_fixed, after_log
from tqdm.asyncio import tqdm
from wordlift_client import (
    EmbeddingRequest,
    ApiClient,
    WebPagesImportsApi,
    WebPageImportRequest,
)

from .create_or_update_entities_factory import create_or_update_entities_factory
from .patch_entities_factory import patch_entities_factory
from ..protocol import (
    WebPageImportProtocolInterface,
    load_override_class,
    DefaultWebPageImportProtocol,
    Context,
)
from ..url_source import UrlSource, Url
from ..utils import create_delayed

logger = logging.getLogger(__name__)


class KgImportWorkflow:
    context: Context
    concurrency: int
    embedding_request: EmbeddingRequest
    url_source: UrlSource
    web_page_import_callback: WebPageImportProtocolInterface
    web_page_types: list[str]

    def __init__(
        self,
        context: Context,
        url_source: UrlSource,
        embedding_properties: list[str] | None = None,
        web_page_types: list[str] | None = None,
        web_page_import_callback: WebPageImportProtocolInterface | None = None,
        concurrency: int = min(cpu_count(), 4),
    ) -> None:
        self.context = context
        self.url_source = url_source
        self.embedding_request = EmbeddingRequest(
            properties=[
                "http://schema.org/headline",
                "http://schema.org/abstract",
                "http://schema.org/text",
            ]
            if embedding_properties is None
            else embedding_properties
        )
        self.web_page_types = (
            ["http://schema.org/Article"] if web_page_types is None else web_page_types
        )

        if web_page_import_callback is None:
            self.web_page_import_callback = load_override_class(
                name="web_page_import_protocol",
                class_name="WebPageImportProtocol",
                # Default class to use in case of missing override.
                default_class=DefaultWebPageImportProtocol,
                context=context,
            )

        self.concurrency = concurrency

    async def run(self):
        await self._run_url_import()
        await self._run_graph_queue()
        await self._run_entity_patch_queue()

    async def _run_url_import(self):
        list_url = []
        async for url in self.url_source.urls():
            list_url.append(url)

        @retry(
            # stop=stop_after_attempt(5),  # Retry up to 5 times
            retry=retry_if_exception_type(
                asyncio.TimeoutError
                | aiohttp.client_exceptions.ServerDisconnectedError
                | aiohttp.client_exceptions.ClientConnectorError
                | aiohttp.client_exceptions.ClientPayloadError
            ),
            wait=wait_fixed(2),  # Wait 2 seconds between retries
            after=after_log(logger, logging.WARNING),
            reraise=True,
        )
        async def url_handler(url: Url) -> None:
            async with ApiClient(self.context.client_configuration) as client:
                api_instance = WebPagesImportsApi(client)

                request = WebPageImportRequest(
                    url=url.value,
                    id=None if url.iri is None else url.iri,
                    embedding=self.embedding_request,
                    output_types=self.web_page_types,
                    id_generator="headline-with-url-hash",
                )

                response = await api_instance.create_web_page_imports(
                    web_page_import_request=request, _request_timeout=60.0
                )
                await self.web_page_import_callback.callback(response)

        logger.info("Applying %d URL import request(s)" % len(list_url))

        delayed = create_delayed(url_handler, self.concurrency)
        await tqdm.gather(
            *[delayed()(url) for url in list(list_url)],
            total=len(list_url),
            dynamic_ncols=True,
        )

    async def _run_graph_queue(self):
        queue = self.context.graph_queue

        logger.info("Applying %d graph request(s)" % len(queue))

        delayed = create_delayed(
            await create_or_update_entities_factory(
                configuration=self.context.client_configuration
            ),
            self.concurrency,
        )

        # Run all the queued graphs.
        await tqdm.gather(*[delayed(queue.get()) for _ in range(len(queue))])

    async def _run_entity_patch_queue(self):
        queue = self.context.entity_patch_queue

        logger.info("Applying %d entity patch request(s)" % len(queue))

        delayed = create_delayed(
            await patch_entities_factory(
                configuration=self.context.client_configuration
            ),
            self.concurrency,
        )

        # Run all the queued graphs.
        await tqdm.gather(*[delayed(queue.get()) for _ in range(len(queue))])

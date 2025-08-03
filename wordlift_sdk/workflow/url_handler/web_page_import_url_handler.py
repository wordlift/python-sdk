import asyncio
import logging

import aiohttp
import pydantic_core
from tenacity import (
    retry,
    retry_if_exception_type,
    wait_fixed,
    after_log,
    stop_after_attempt,
)
from wordlift_client import (
    ApiClient,
    WebPagesImportsApi,
    WebPageImportRequest,
    EmbeddingRequest,
)
import wordlift_client
import gql.transport.exceptions

from .url_handler import UrlHandler
from ...protocol import (
    Context,
    WebPageImportProtocolInterface,
    load_override_class,
    DefaultWebPageImportProtocol,
)
from ...url_source import Url

logger = logging.getLogger(__name__)


class WebPageImportUrlHandler(UrlHandler):
    _context: Context
    _embedding_request: EmbeddingRequest
    _web_page_import_callback: WebPageImportProtocolInterface
    _web_page_types: list[str]
    _write_strategy: str

    def __init__(
        self,
        context: Context,
        embedding_properties: list[str],
        web_page_types: list[str],
        web_page_import_callback: WebPageImportProtocolInterface | None = None,
        write_strategy: str = "createOrUpdateModel",
    ):
        self._context = context
        self._embedding_request = EmbeddingRequest(
            properties=embedding_properties,
        )
        self._web_page_types = web_page_types
        if web_page_import_callback is None:
            self._web_page_import_callback = load_override_class(
                name="web_page_import_protocol",
                class_name="WebPageImportProtocol",
                # Default class to use in case of missing override.
                default_class=DefaultWebPageImportProtocol,
                context=context,
            )
        else:
            self._web_page_import_callback = web_page_import_callback

        self._write_strategy = write_strategy

    @retry(
        retry=retry_if_exception_type(
            asyncio.TimeoutError
            | aiohttp.client_exceptions.ServerDisconnectedError
            | aiohttp.client_exceptions.ClientConnectorError
            | aiohttp.client_exceptions.ClientPayloadError
            | aiohttp.client_exceptions.ClientConnectorDNSError
            | pydantic_core._pydantic_core.ValidationError
            | wordlift_client.exceptions.ServiceException
            | gql.transport.exceptions.TransportServerError
            | wordlift_client.exceptions.BadRequestException
            | aiohttp.client_exceptions.ClientOSError
        ),
        wait=wait_fixed(2),  # Wait 2 seconds between retries
        after=after_log(logger, logging.WARNING),
        stop=stop_after_attempt(5),
    )
    async def __call__(self, url: Url) -> None:
        async with ApiClient(self._context.client_configuration) as client:
            api_instance = WebPagesImportsApi(client)

            request = WebPageImportRequest(
                url=url.value,
                id=None if url.iri is None else url.iri,
                embedding=self._embedding_request,
                output_types=self._web_page_types,
                id_generator="headline-with-url-hash",
                write_strategy=self._write_strategy,
            )

            try:
                response = await api_instance.create_web_page_imports(
                    web_page_import_request=request, _request_timeout=120.0
                )
                await self._web_page_import_callback.callback(response)
            except Exception as e:
                logger.error("Error importing Web Page %s" % url.value, exc_info=e)
                raise e

import logging

from wordlift_client import (
    ApiClient,
    WebPagesImportsApi,
    WebPageImportRequest,
    WebPageImportResponse,
    EmbeddingRequest,
    WebPageImportFetchOptions,
)

from .url_handler import UrlHandler
from ...protocol import (
    Context,
    WebPageImportProtocolInterface,
    load_override_class,
    DefaultWebPageImportProtocol,
)
from ...protocol.retry_policy import retry_transient
from ...url_source import Url

logger = logging.getLogger(__name__)


class WebPageImportUrlHandler(UrlHandler):
    _context: Context
    _embedding_request: EmbeddingRequest
    _fetch_options: WebPageImportFetchOptions | None
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
        fetch_options: WebPageImportFetchOptions | None = None,
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
        self._fetch_options = fetch_options

    @retry_transient(logger)
    async def _import(self, url: Url) -> WebPageImportResponse:
        async with ApiClient(self._context.client_configuration) as client:
            api_instance = WebPagesImportsApi(client)

            request = WebPageImportRequest(
                url=url.value,
                id=None if url.iri is None else url.iri,
                embedding=self._embedding_request,
                output_types=self._web_page_types,
                id_generator="headline-with-url-hash",
                write_strategy=self._write_strategy,
                fetch_options=self._fetch_options,
            )

            return await api_instance.create_web_page_imports(
                web_page_import_request=request, _request_timeout=120.0
            )

    async def __call__(self, url: Url) -> None:
        # Only the import request is retried here. The callback writes the
        # graph through queues that retry on their own, so retrying it again
        # would multiply the writes.
        response = await self._import(url)
        await self._web_page_import_callback.callback(response)

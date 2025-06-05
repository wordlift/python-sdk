import asyncio
import logging
from os import cpu_count

from tenacity import retry, retry_if_exception_type, wait_fixed, before_log
from tqdm.asyncio import tqdm
from wordlift_client import EmbeddingRequest, ApiClient, WebPagesImportsApi, WebPageImportRequest

from ..protocol import WebPageImportProtocolInterface, load_override_class, DefaultWebPageImportProtocol, Context
from ..url_provider import UrlProvider, Url
from ..utils import create_delayed

logger = logging.getLogger(__name__)


class KgImportWorkflow:
    context: Context
    concurrency: int
    embedding_request: EmbeddingRequest
    url_provider: UrlProvider
    web_page_import_callback: WebPageImportProtocolInterface
    web_page_types: list[str]

    def __init__(
            self,
            context: Context,
            url_provider: UrlProvider,
            embedding_properties: list[str] | None = None,
            web_page_types: list[str] | None = None,
            web_page_import_callback: WebPageImportProtocolInterface | None = None,
            concurrency: int = min(cpu_count(), 4),
    ) -> None:
        self.context = context
        self.url_provider = url_provider
        self.embedding_request = EmbeddingRequest(
            properties=
            [
                'http://schema.org/headline',
                'http://schema.org/abstract',
                'http://schema.org/text'
            ] if embedding_properties is None else embedding_properties
        )
        self.web_page_types = ['http://schema.org/Article'] if web_page_types is None else web_page_types

        if web_page_import_callback is None:
            self.web_page_import_callback = load_override_class(
                name="web_page_import_protocol",
                class_name="WebPageImportProtocolInterface",
                # Default class to use in case of missing override.
                default_class=DefaultWebPageImportProtocol,
                context=context,
            )

        self.concurrency = concurrency

    async def run(self):
        list_url = []
        async for url in self.url_provider.urls():
            list_url.append(url)

        @retry(
            # stop=stop_after_attempt(5),  # Retry up to 5 times
            retry=retry_if_exception_type(asyncio.TimeoutError),
            wait=wait_fixed(2),  # Wait 2 seconds between retries
            before=before_log(logger, logging.DEBUG)

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
                    web_page_import_request=request,
                    _request_timeout=60.0
                )
                await self.web_page_import_callback.callback(response)

        delayed = create_delayed(url_handler, self.concurrency)
        results = await tqdm.gather(
            *[delayed()(url) for url in list(list_url)],
            total=len(list_url),
            dynamic_ncols=True
        )

import logging

import wordlift_client
from tenacity import retry, stop_after_attempt, wait_fixed
from wordlift_client import SitemapImportsApi, SitemapImportRequest, EmbeddingRequest

from ..import_url_protocol_interface import ImportUrlProtocolInterface, ImportUrlInput

logger = logging.getLogger(__name__)


class DefaultImportUrlProtocol(ImportUrlProtocolInterface):

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2)
    )
    async def import_url(self, import_url_input: ImportUrlInput) -> None:
        configuration = self.context.configuration
        types = self.context.types
        url_list = import_url_input.url_list

        async with wordlift_client.ApiClient(configuration) as api_client:
            imports_api = SitemapImportsApi(api_client)
            request = SitemapImportRequest(
                embedding=EmbeddingRequest(
                    properties=["http://schema.org/headline", "http://schema.org/abstract",
                                "http://schema.org/text"]
                ),
                output_types=list(types),
                urls=list(url_list),
                overwrite=True,
                id_generator="headline-with-url-hash"
            )

            try:
                await imports_api.create_sitemap_import(sitemap_import_request=request)
            except Exception as e:
                logger.error("Error importing URLs: %s", e)

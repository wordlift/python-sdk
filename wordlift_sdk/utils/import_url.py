import logging
from typing import Callable, Awaitable

from tenacity import retry, stop_after_attempt, wait_fixed
from wordlift_client import Configuration, SitemapImportsApi, SitemapImportRequest, EmbeddingRequest

logger = logging.getLogger(__name__)


async def import_url_factory(configuration: Configuration, types: set[str]) -> Callable[[set[str]], Awaitable[None]]:
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(2)
    )
    async def import_url(url_list: set[str]) -> None:
        import wordlift_client

        async with wordlift_client.ApiClient(configuration) as api_client:
            imports_api = SitemapImportsApi(api_client)
            request = SitemapImportRequest(
                embedding=EmbeddingRequest(
                    properties=["http://schema.org/headline", "http://schema.org/abstract", "http://schema.org/text"]
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

    return import_url

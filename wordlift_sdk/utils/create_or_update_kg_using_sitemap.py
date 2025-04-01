import logging
from os import cpu_count
from typing import Callable, Awaitable
from tqdm.asyncio import tqdm
from wordlift_client import EntityPatchRequest, Configuration
from .create_dataframe_of_entities_by_types import create_dataframe_of_entities_by_types
from .import_url import import_url_factory
from .delayed import delayed
import advertools as adv

from .. import entity

logger = logging.getLogger(__name__)


async def no_op(entity_id: str, html: str) -> list[EntityPatchRequest]:
    return list()


async def create_or_update_kg_using_sitemap(
        configuration: Configuration,
        key: str,
        sitemap_url: str,
        types: set[str],
        concurrency: int = cpu_count(),
        import_url_callback: Callable[[set[str]], Awaitable[None]] = None,
        parse_html_callback: Callable[[str, str], Awaitable[list[EntityPatchRequest]]] = no_op
) -> None:
    # Set the default callback.
    if import_url_callback is None:
        import_url_callback = await import_url_factory(configuration=configuration, types=types)

    # Get the list of URLs from the sitemap (`loc` column)
    sitemap_df = adv.sitemap_to_df(sitemap_url)

    # Get the data from the KG to determine which URLs are already imported and which not.
    kg_df = await create_dataframe_of_entities_by_types(key=key, types=types)

    # Get the list of missing URLs, these are the URLs we'll import.
    missing_url_list = list(set(sitemap_df['loc']) - set(kg_df['url']))

    logger.info('Importing %d entities...', len(missing_url_list))

    # Import the URLs by calling the `import_url` method. We use `delayed` to parallelize work.
    await tqdm.gather(*[delayed(import_url_callback, concurrency)([url]) for url in missing_url_list],
                      total=len(missing_url_list))

    # Reload the Kg after the import to get the list of URLs that are missing the `keywords` field.
    # @@TODO we can call a different graphql query that filters already by keywords not present or empty instead of filtering client-side.
    kg_df = await create_dataframe_of_entities_by_types(key=key, types=types)

    # Filter the KG to list only the URLs without `keywords`.
    no_keywords_df = kg_df[kg_df['keywords'].isna()]

    logger.info('Enriching %d entities...', len(no_keywords_df))

    # Enrich the Graph, notice that here we pass our callback `parse_html` which will return Patch requests, no need to deal with the actual API. We're polite and not making more than 2 concurrent reqs.
    await tqdm.gather(
        *[delayed(entity.enrich(configuration, parse_html_callback), concurrency)(row) for index, row in
          no_keywords_df.iterrows()],
        total=len(no_keywords_df)
    )

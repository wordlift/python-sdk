import logging
from os import cpu_count

from tqdm.asyncio import tqdm
from wordlift_client import Configuration

from wordlift_sdk import entity
from wordlift_sdk.kg.manager.urlprovider.list_url_provider import ListUrlProvider
from wordlift_sdk.kg.manager.urlprovider.sitemap_url_provider import SitemapUrlProvider
from wordlift_sdk.kg.manager.urlprovider.url_provider import UrlProvider
from wordlift_sdk.utils import create_dataframe_of_url_iri, create_delayed
from wordlift_sdk.utils.create_dataframe_of_entities_by_types import create_dataframe_of_entities_by_types
from wordlift_sdk.wordlift.sitemap_import.protocol.default import DefaultImportUrlProtocol, DefaultParseHtmlProtocol
from wordlift_sdk.wordlift.sitemap_import.protocol.import_url_protocol_interface import ImportUrlProtocolInterface, \
    ImportUrlInput
from wordlift_sdk.wordlift.sitemap_import.protocol.parse_html_protocol_interface import ParseHtmlProtocolInterface
from wordlift_sdk.wordlift.sitemap_import.protocol.protocol_context import ProtocolContext

logger = logging.getLogger(__name__)


async def create_or_update_kg_using_urls(
        configuration: Configuration,
        key: str,
        urls: set[str],
        types: set[str],
        concurrency: int = cpu_count(),
        import_url_protocol: ImportUrlProtocolInterface = None,
        parse_html_protocol: ParseHtmlProtocolInterface = None,
        overwrite: bool = False,
) -> None:
    # Create a ListUrlProvider
    url_provider = ListUrlProvider(list(urls))

    # Use the new method with the provider
    await create_or_update_kg_using_url_provider(
        configuration=configuration,
        key=key,
        url_provider=url_provider,
        types=types,
        concurrency=concurrency,
        import_url_protocol=import_url_protocol,
        parse_html_protocol=parse_html_protocol,
        overwrite=overwrite
    )


async def create_or_update_kg_using_url_provider(
        configuration: Configuration,
        key: str,
        url_provider: UrlProvider,
        types: set[str],
        concurrency: int = cpu_count(),
        import_url_protocol: ImportUrlProtocolInterface = None,
        parse_html_protocol: ParseHtmlProtocolInterface = None,
        overwrite: bool = False,
) -> None:
    # Collect URLs from the provider
    urls = set()
    async for url in url_provider.urls():
        urls.add(url.value)

    # Set the default callback.
    if import_url_protocol is None:
        import_url_protocol = DefaultImportUrlProtocol(
            context=ProtocolContext(configuration=configuration, types=list(types)))

    if parse_html_protocol is None:
        parse_html_protocol = DefaultParseHtmlProtocol(
            context=ProtocolContext(configuration=configuration, types=list(types)))

    if overwrite:
        missing_url_list = list(urls)
    else:
        # Get the data from the KG to determine which URLs are already imported and which not.
        kg_df = await create_dataframe_of_entities_by_types(key=key, types=types)

        # Get the list of missing URLs, these are the URLs we'll import.
        missing_url_list = list(urls - set(kg_df['url']))

    logger.info('Importing %d entities...', len(missing_url_list))

    # Import the URLs by calling the `import_url` method. We use `delayed` to parallelize work.
    await tqdm.gather(
        *[delayed(import_url_protocol.import_url, concurrency)(ImportUrlInput(url_list=[url])) for url in
          missing_url_list],
        total=len(missing_url_list))

    kg_df = await create_dataframe_of_url_iri(key=key, url_list=missing_url_list)

    logger.info('Enriching %d entities...', len(kg_df))

    # Enrich the Graph, notice that here we pass our callback `parse_html` which will return Patch requests, no need to deal with the actual API. We're polite and not making more than 2 concurrent reqs.
    delayed = create_delayed(entity.enrich(configuration, parse_html_protocol.parse_html), concurrency)
    await tqdm.gather(*[delayed(row) for index, row in kg_df.iterrows()], total=len(kg_df))


async def create_or_update_kg_using_sitemap(
        configuration: Configuration,
        key: str,
        sitemap_url: str,
        types: set[str],
        concurrency: int = cpu_count(),
        import_url_protocol: ImportUrlProtocolInterface = None,
        parse_html_protocol: ParseHtmlProtocolInterface = None
) -> None:
    # Create a SitemapUrlProvider
    url_provider = SitemapUrlProvider(sitemap_url)

    # Use the new method with the provider
    await create_or_update_kg_using_url_provider(
        configuration=configuration,
        key=key,
        url_provider=url_provider,
        types=types,
        concurrency=concurrency,
        import_url_protocol=import_url_protocol,
        parse_html_protocol=parse_html_protocol
    )

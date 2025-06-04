import logging
from dataclasses import dataclass, field
from os import cpu_count
from pathlib import Path
from typing import Optional

import gspread
from tqdm.asyncio import tqdm
from wordlift_client import AccountInfo, Configuration

from wordlift_sdk.graph import GraphQueue
from wordlift_sdk.graph.ttl_liquid import TtlLiquidGraphFactory
from wordlift_sdk.graphql.client import GraphQlClient, GraphQlClientFactory
from wordlift_sdk.id_generator import IdGenerator
from wordlift_sdk.kg.manager.urlprovider import UrlProviderFactory, UrlProviderFactoryInput, UrlProvider
from wordlift_sdk.utils import get_me, create_dataframe_of_entities_by_types, delayed
from wordlift_sdk.wordlift.sitemap_import.create_or_update_kg import create_or_update_kg_using_url_provider
from wordlift_sdk.wordlift.sitemap_import.protocol import ProtocolContext, load_override_class, \
    DefaultImportUrlProtocol, DefaultParseHtmlProtocol, ImportUrlProtocolInterface, ParseHtmlProtocolInterface, \
    ImportUrlInput

logger = logging.getLogger(__name__)


@dataclass
class KgImportWorkflowConfiguration:
    client_configuration: Configuration
    key: str
    sitemap_url: Optional[str] = None
    sheets_url: Optional[str] = None
    sheets_name: Optional[str] = None
    sheets_service_account: Optional[str] = None
    urls: Optional[list[str]] = None
    output_types: list[str] = field(default_factory=lambda: ['http://schema.org/Article'])
    templates_path: Path = Path("data/templates")

    def __post_init__(self):
        has_sitemap = self.sitemap_url is not None

        has_sheets = all([
            self.sheets_url,
            self.sheets_name,
            self.sheets_service_account,
        ])

        has_urls = bool(self.urls)

        mode_count = sum([has_sitemap, has_sheets, has_urls])
        if mode_count != 1:
            raise ValueError(
                "You must set exactly one of the following:\n"
                "- sitemap_url\n"
                "- all of sheets_url, sheets_name, and sheets_service_account\n"
                "- urls (non-empty list)"
            )


class KgImportWorkflow:
    account: AccountInfo
    configuration: KgImportWorkflowConfiguration
    context: ProtocolContext
    graphql_client: GraphQlClient
    import_url_protocol: ImportUrlProtocolInterface
    parse_html_protocol: ParseHtmlProtocolInterface
    ttl_liquid_graph_factory: TtlLiquidGraphFactory
    url_provider: UrlProvider

    def __init__(self,
                 account: AccountInfo,
                 configuration: KgImportWorkflowConfiguration,
                 context: ProtocolContext,
                 graphql_client: GraphQlClient,
                 import_url_protocol: ImportUrlProtocolInterface,
                 parse_html_protocol: ParseHtmlProtocolInterface,
                 ttl_liquid_graph_factory: TtlLiquidGraphFactory,
                 url_provider: UrlProvider
                 ):
        self.account = account
        self.configuration = configuration
        self.context = context
        self.graphql_client = graphql_client
        self.import_url_protocol = import_url_protocol
        self.parse_html_protocol = parse_html_protocol
        self.ttl_liquid_graph_factory = ttl_liquid_graph_factory
        self.url_provider = url_provider

    async def start(self):
        # Take all the graphs from the local graphs folder, by default, it's `data/templates`. These are liquid
        # templates.
        async for graph in self.ttl_liquid_graph_factory.graphs(self.configuration.templates_path.resolve()):
            self.context.graph_queue.put(graph)

        # Import URLs.
        logger.info("Importing...")
        await self.create_or_update_kg_using_url_provider(
            configuration=self.configuration.client_configuration,
            key=self.configuration.key,
            types=set(self.configuration.output_types),
            concurrency=1,
        )

    async def create_or_update_kg_using_url_provider(
            self,
            configuration: Configuration,
            key: str,
            types: set[str],
            concurrency: int = cpu_count(),
            overwrite: bool = False,
    ) -> None:
        # Collect URLs from the provider
        urls = set()
        async for url in self.url_provider.urls():
            urls.add(url.value)

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
            *[delayed(self.import_url_protocol.import_url, concurrency)(ImportUrlInput(url_list=[url])) for url in
              missing_url_list],
            total=len(missing_url_list))

        kg_df = await create_dataframe_of_url_iri(key=key, url_list=missing_url_list)

        logger.info('Enriching %d entities...', len(kg_df))

        # Enrich the Graph, notice that here we pass our callback `parse_html` which will return Patch requests, no need to deal with the actual API. We're polite and not making more than 2 concurrent reqs.
        await tqdm.gather(
            *[delayed(entity.enrich(configuration, parse_html_protocol.parse_html), concurrency)(
                row
            ) for index, row in
                kg_df.iterrows()],
            total=len(kg_df)
        )

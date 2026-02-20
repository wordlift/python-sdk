from os import cpu_count
from wordlift_client import Configuration, AccountInfo, WebPageImportFetchOptions

from ..client.client_configuration_factory import ClientConfigurationFactory
from ..configuration import ConfigurationProvider
from ..graphql.client import GraphQlClientFactory, GraphQlClient, GqlClientProvider
from ..ingestion.factory import create_source_registry
from ..ingestion.resolver import resolve_ingestion_config_from_provider
from ..id_generator import IdGenerator
from ..protocol import Context
from ..protocol.entity_patch import EntityPatchQueue
from ..protocol.graph import GraphQueue
from ..url_source import (
    UrlSource,
)
from ..url_source.adapter_url_source import AdapterUrlSource
from ..url_source.new_or_changed_url_source import NewOrChangedUrlSource
from ..utils import get_me
from ..workflow.kg_import_workflow import KgImportWorkflow
from ..workflow.url_handler import WebPageImportUrlHandler
from ..workflow.url_handler.default_url_handler import DefaultUrlHandler
from ..workflow.url_handler.search_console_url_handler import SearchConsoleUrlHandler
from ..workflow.url_handler.url_handler import UrlHandler


class ApplicationContainer:
    _api_url: str
    _client_configuration: Configuration
    _configuration_provider: ConfigurationProvider
    _key: str

    _context: Context | None = None
    _graphql_client: GraphQlClient | None = None

    def __init__(self, configuration_provider: ConfigurationProvider | None = None):
        self._configuration_provider = (
            configuration_provider or ConfigurationProvider.create()
        )
        self._api_url = self._configuration_provider.get_value(
            "API_URL", "https://api.wordlift.io"
        )
        self._key = self._configuration_provider.get_value("WORDLIFT_KEY")
        self._client_configuration = ClientConfigurationFactory(
            key=self._key,
            api_url=self._api_url,
        ).create()

    async def get_account(self) -> AccountInfo:
        return await get_me(configuration=self._client_configuration)

    async def get_context(self) -> Context:
        if not self._context:
            account = await self.get_account()
            self._context = Context(
                account=account,
                client_configuration=self._client_configuration,
                configuration_provider=self._configuration_provider,
                id_generator=IdGenerator(account=account),
                graph_queue=GraphQueue(client_configuration=self._client_configuration),
                entity_patch_queue=EntityPatchQueue(
                    client_configuration=self._client_configuration
                ),
            )

        return self._context

    async def create_web_page_import_url_handler(self) -> WebPageImportUrlHandler:
        write_strategy = self._configuration_provider.get_value(
            "WEB_PAGE_IMPORT_WRITE_STRATEGY", "createOrUpdateModel"
        )
        fetch_options = WebPageImportFetchOptions(
            mode=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_MODE", "default"
            ),
            render_js=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_RENDER_JS", None
            ),
            wait_for=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_WAIT_FOR", None
            ),
            country_code=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_COUNTRY_CODE", None
            ),
            premium_proxy=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_PREMIUM_PROXY", None
            ),
            block_ads=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_BLOCK_ADS", None
            ),
            timeout=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_TIMEOUT", None
            ),
        )
        return WebPageImportUrlHandler(
            context=await self.get_context(),
            embedding_properties=self._configuration_provider.get_value(
                "EMBEDDING_PROPERTIES",
                [
                    "http://schema.org/headline",
                    "http://schema.org/abstract",
                    "http://schema.org/text",
                ],
            ),
            web_page_types=self._configuration_provider.get_value(
                "WEB_PAGE_TYPES", ["http://schema.org/Article"]
            ),
            write_strategy=write_strategy,
            fetch_options=fetch_options,
        )

    async def create_search_console_url_handler(self):
        return SearchConsoleUrlHandler(
            context=await self.get_context(),
            graphql_client=await self.get_graphql_client(),
        )

    async def create_multi_url_handler(self):
        handlers: list[UrlHandler] = [
            await self.create_web_page_import_url_handler(),
        ]
        if (
            self._configuration_provider.get_value("GOOGLE_SEARCH_CONSOLE", True)
            is True
        ):
            handlers.append(await self.create_search_console_url_handler())

        return DefaultUrlHandler(url_handler_list=handlers)

    async def create_kg_import_workflow(self) -> KgImportWorkflow:
        concurrency = self._configuration_provider.get_value(
            "CONCURRENCY", min(cpu_count(), 4)
        )
        return KgImportWorkflow(
            context=await self.get_context(),
            url_source=await self.create_new_or_changed_source(),
            url_handler=await self.create_multi_url_handler(),
            concurrency=concurrency,
        )

    async def create_graphql_client_factory(self) -> GraphQlClientFactory:
        return GraphQlClientFactory(key=self._key, api_url=self._api_url + "/graphql")

    async def create_gql_client_provider(self) -> GqlClientProvider:
        graphql_client_factory = await self.create_graphql_client_factory()
        return graphql_client_factory.create_provider()

    async def get_graphql_client(self) -> GraphQlClient:
        if self._graphql_client is None:
            graphql_client_factory = await self.create_graphql_client_factory()
            self._graphql_client = graphql_client_factory.create()

        return self._graphql_client

    async def create_url_source(self) -> UrlSource:
        resolved = resolve_ingestion_config_from_provider(self._configuration_provider)
        adapter = create_source_registry().resolve(resolved.source_name)
        return AdapterUrlSource(adapter=adapter, config=resolved)

    async def create_new_or_changed_source(self) -> UrlSource:
        overwrite = self._configuration_provider.get_value("OVERWRITE", False)
        return NewOrChangedUrlSource(
            url_provider=await self.create_url_source(),
            graphql_client=await self.get_graphql_client(),
            overwrite=overwrite,
        )

    async def create_url_source_with_overwrite(self) -> UrlSource:
        return await self.create_new_or_changed_source()

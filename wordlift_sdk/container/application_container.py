import re
from dataclasses import dataclass
from os import cpu_count
from typing import Optional, Union

import gspread
from google.auth.credentials import Credentials
from gspread import Client
from wordlift_client import Configuration, AccountInfo

from ..client.client_configuration_factory import ClientConfigurationFactory
from ..configuration import ConfigurationProvider
from ..graphql.client import GraphQlClientFactory, GraphQlClient, GqlClientProvider
from ..id_generator import IdGenerator
from ..protocol import Context
from ..protocol.entity_patch import EntityPatchQueue
from ..protocol.graph import GraphQueue
from ..url_source import (
    SitemapUrlSource,
    GoogleSheetsUrlSource,
    ListUrlSource,
    UrlSource,
)
from ..url_source.new_or_changed_url_source import NewOrChangedUrlSource
from ..utils import get_me
from ..workflow.kg_import_workflow import KgImportWorkflow
from ..workflow.url_handler import WebPageImportUrlHandler
from ..workflow.url_handler.default_url_handler import DefaultUrlHandler
from ..workflow.url_handler.search_console_url_handler import SearchConsoleUrlHandler
from ..workflow.url_handler.url_handler import UrlHandler


@dataclass
class UrlSourceInput:
    """
    Input structure for the UrlProviderFactory.

    This class holds all possible parameters needed to create any of the supported URL providers.
    The factory will use these parameters to determine which provider to create based on availability.
    """

    sitemap_url: Optional[str] = None
    sitemap_url_pattern: Optional[str] = None
    sheets_url: Optional[str] = None
    sheets_name: Optional[str] = None
    sheets_creds_or_client: Optional[Union[Credentials, Client]] = None
    urls: Optional[list[str]] = None


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
        # Try to read the configuration from the `config/default.py` file.
        sitemap_url = self._configuration_provider.get_value("SITEMAP_URL")
        sitemap_url_pattern = self._configuration_provider.get_value(
            "SITEMAP_URL_PATTERN", None
        )
        sheets_url = self._configuration_provider.get_value("SHEETS_URL")
        sheets_name = self._configuration_provider.get_value("SHEETS_NAME")
        sheets_service_account = self._configuration_provider.get_value(
            "SHEETS_SERVICE_ACCOUNT"
        )
        urls = self._configuration_provider.get_value("URLS")

        if (
            sitemap_url is None
            and urls is None
            and (
                sheets_url is None
                or sheets_name is None
                or sheets_service_account is None
            )
        ):
            raise ValueError(
                "One of `sitemap_url` or `sheets_url`/`sheets_name`/`sheets_service_account` is required."
            )

        input_params = UrlSourceInput(
            sitemap_url=sitemap_url,
            sitemap_url_pattern=sitemap_url_pattern,
            sheets_url=sheets_url,
            sheets_name=sheets_name,
            sheets_creds_or_client=(
                gspread.service_account(filename=sheets_service_account)
                if sheets_service_account
                else None
            ),
            urls=urls,
        )

        # Try to create a SitemapUrlProvider if sitemap_url is provided
        if input_params.sitemap_url:
            return SitemapUrlSource(
                input_params.sitemap_url,
                re.compile(input_params.sitemap_url_pattern)
                if input_params.sitemap_url_pattern
                else None,
            )

        # Try to create a GoogleSheetsUrlProvider if all required sheets parameters are provided
        if (
            input_params.sheets_url
            and input_params.sheets_name
            and input_params.sheets_creds_or_client
        ):
            return GoogleSheetsUrlSource(
                input_params.sheets_creds_or_client,
                input_params.sheets_url,
                input_params.sheets_name,
            )

        # Try to create a ListUrlProvider if urls is provided
        if input_params.urls:
            return ListUrlSource(input_params.urls)

        # If we get here, none of the required parameters were provided
        raise ValueError(
            "No valid parameters provided to create a URL provider. "
            "Please provide either sitemap_url, all sheets parameters "
            "(sheets_url, sheets_name, sheets_creds_or_client), or urls."
        )

    async def create_new_or_changed_source(self) -> UrlSource:
        overwrite = self._configuration_provider.get_value("OVERWRITE", False)
        return NewOrChangedUrlSource(
            url_provider=await self.create_url_source(),
            graphql_client=await self.get_graphql_client(),
            overwrite=overwrite,
        )

    async def create_url_source_with_overwrite(self) -> UrlSource:
        return await self.create_new_or_changed_source()

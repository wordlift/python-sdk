import logging
import os.path
import re

import pytest
import pytest_asyncio
import wordlift_client
from wordlift_client import AccountInfo

import wordlift_sdk.client
import wordlift_sdk.utils
from wordlift_sdk.configuration import ConfigurationProvider
from wordlift_sdk.container.application_container import ApplicationContainer
from wordlift_sdk.graphql.client import GraphQlClient, GraphQlClientFactory
from wordlift_sdk.id_generator import IdGenerator
from wordlift_sdk.protocol import Context, DefaultWebPageImportProtocol
from wordlift_sdk.protocol.entity_patch import EntityPatchQueue
from wordlift_sdk.protocol.graph import GraphQueue
from wordlift_sdk.url_source import UrlSource, SitemapUrlSource
from wordlift_sdk.url_source.new_or_changed_url_source import NewOrChangedUrlSource
from wordlift_sdk.workflow.kg_import_workflow import KgImportWorkflow
from wordlift_sdk.workflow.url_handler import WebPageImportUrlHandler
from wordlift_sdk.workflow.url_handler.url_handler import UrlHandler

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.fixture
def test_key() -> str:
    return "key0585449788059158"


@pytest.fixture
def test_api_url(wiremock_url: str) -> str:
    return wiremock_url + "/test_kg_import_workflow"


@pytest.fixture
def test_sitemap_url(test_api_url: str) -> str:
    return test_api_url + "/MakaleSiteMap.xml"


@pytest.fixture
def test_sitemap_url_pattern() -> str:
    return r"^https://www.herkesicinguzellik.com/makale/.*$"


@pytest.fixture
def client_configuration(
    wiremock_url: str, test_key: str, test_api_url: str
) -> wordlift_client.Configuration:
    return wordlift_sdk.client.ClientConfigurationFactory(
        key=test_key, api_url=test_api_url
    ).create()


@pytest.fixture
def graphql_client(test_key: str, test_api_url: str) -> GraphQlClient:
    return GraphQlClientFactory(
        key=test_key, api_url=test_api_url + "/graphql"
    ).create()


@pytest.fixture
def url_provider(
    graphql_client: GraphQlClient, test_sitemap_url: str, test_sitemap_url_pattern: str
) -> UrlSource:
    return NewOrChangedUrlSource(
        url_provider=SitemapUrlSource(
            sitemap_url=test_sitemap_url,
            pattern=re.compile(test_sitemap_url_pattern),
        ),
        graphql_client=graphql_client,
    )


@pytest_asyncio.fixture
async def account(client_configuration: wordlift_client.Configuration) -> AccountInfo:
    return await wordlift_sdk.utils.get_me(client_configuration)


@pytest.fixture
def context(
    account: AccountInfo, client_configuration: wordlift_client.Configuration
) -> Context:
    return Context(
        account=account,
        client_configuration=client_configuration,
        id_generator=IdGenerator(account=account),
        graph_queue=GraphQueue(client_configuration=client_configuration),
        entity_patch_queue=EntityPatchQueue(client_configuration=client_configuration),
    )


@pytest_asyncio.fixture
async def url_handler(context: Context) -> UrlHandler:
    return WebPageImportUrlHandler(
        context=context,
        embedding_properties=[
            "http://schema.org/headline",
            "http://schema.org/abstract",
            "http://schema.org/text",
        ],
        web_page_types=["http://schema.org/WebPage"],
        web_page_import_callback=DefaultWebPageImportProtocol(context=context),
    )


@pytest.fixture
def kg_import_workflow(
    context: Context, url_provider: UrlSource, url_handler: UrlHandler
) -> KgImportWorkflow:
    return KgImportWorkflow(
        context=context, url_source=url_provider, concurrency=5, url_handler=url_handler
    )


@pytest.mark.asyncio
async def test_playground(kg_import_workflow: KgImportWorkflow) -> None:
    await kg_import_workflow.run()


@pytest.fixture
def application_container(
    test_api_url: str,
    test_sitemap_url: str,
    test_key: str,
    test_sitemap_url_pattern: str,
    monkeypatch,
) -> ApplicationContainer:
    monkeypatch.setenv("API_URL", test_api_url)
    monkeypatch.setenv("SITEMAP_URL", test_sitemap_url)
    monkeypatch.setenv("SITEMAP_URL_PATTERN", test_sitemap_url_pattern)
    monkeypatch.setenv("WORDLIFT_KEY", test_key)
    return ApplicationContainer(
        configuration_provider=ConfigurationProvider.create(
            os.path.join(os.path.dirname(__file__), "config/default.py")
        )
    )


@pytest.mark.asyncio
async def test_create_kg_import_workflow(application_container: ApplicationContainer):
    kg_import_workflow = await application_container.create_kg_import_workflow()
    await kg_import_workflow.run()

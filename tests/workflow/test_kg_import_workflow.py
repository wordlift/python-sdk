import logging
import re

import pytest
import wordlift_client
from wordlift_client import AccountInfo

import wordlift_sdk.client
from wordlift_sdk.graphql.client import GraphQlClient, GraphQlClientFactory
from wordlift_sdk.protocol import Context
from wordlift_sdk.url_source import UrlSource, SitemapUrlSource
from wordlift_sdk.url_source.new_or_changed_url_source import NewOrChangedUrlSource
from wordlift_sdk.utils.delayed import create_delayed
from wordlift_sdk.workflow.kg_import_workflow import KgImportWorkflow

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.fixture
def test_key() -> str:
    return 'key0585449788059158'


@pytest.fixture
def test_api_url(wiremock_url: str) -> str:
    return wiremock_url + '/test_kg_import_workflow'


@pytest.fixture
def client_configuration(wiremock_url: str, test_key: str, test_api_url: str) -> wordlift_client.Configuration:
    return wordlift_sdk.client.ClientConfigurationFactory(key=test_key, api_url=test_api_url).create()


@pytest.fixture
def graphql_client(test_key: str, test_api_url: str) -> GraphQlClient:
    return GraphQlClientFactory(key=test_key, api_url=test_api_url + '/graphql').create()


@pytest.fixture
def url_provider(graphql_client: GraphQlClient) -> UrlSource:
    return NewOrChangedUrlSource(
        url_provider=SitemapUrlSource(
            sitemap_url='https://www.herkesicinguzellik.com/MakaleSiteMap.xml',
            pattern=re.compile(r'^https://www.herkesicinguzellik.com/makale/.*$'),
        ),
        graphql_client=graphql_client
    )


@pytest.fixture
async def account(client_configuration: wordlift_client.Configuration) -> AccountInfo:
    return await wordlift_sdk.utils.get_me(client_configuration)


@pytest.fixture
def context(account: AccountInfo, client_configuration: wordlift_client.Configuration) -> Context:
    return Context(account=account, client_configuration=client_configuration)


@pytest.fixture
def kg_import_workflow(context: Context, url_provider: UrlSource, ) -> KgImportWorkflow:
    return KgImportWorkflow(
        context=context,
        url_source=url_provider,
        concurrency=5
    )


@pytest.mark.asyncio
async def test_playground(kg_import_workflow: KgImportWorkflow) -> None:
    await kg_import_workflow.run()

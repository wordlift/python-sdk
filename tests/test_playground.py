import asyncio
import logging
import re

import pytest
import wordlift_client
from tenacity import retry, wait_fixed, retry_if_exception_type, before_log
from tqdm.asyncio import tqdm
from wordlift_client import WebPageImportRequest, EmbeddingRequest, WebPageImportResponse

import wordlift_sdk.client
from wordlift_sdk.graphql.client import GraphQlClient, GraphQlClientFactory
from wordlift_sdk.kg.manager.urlprovider import UrlProvider, SitemapUrlProvider
from wordlift_sdk.kg.manager.urlprovider.new_or_changed_url_provider import NewOrChangedUrlProvider
from wordlift_sdk.utils.delayed import create_delayed

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.fixture
def test_key() -> str:
    return 'MKsuLUHSlSRBBZvrJAr28DrTz4ig1HBXIDeEDEz9weC5DnLO56HLeiIoFxDyTiNW'


@pytest.fixture
def test_api_url() -> str:
    return 'https://api.wordlift.io'


@pytest.fixture
def client_configuration(wiremock_url: str, test_key: str, test_api_url: str) -> wordlift_client.Configuration:
    return wordlift_sdk.client.ClientConfigurationFactory(key=test_key, api_url=test_api_url).create()


@pytest.fixture
def graphql_client(test_key: str, test_api_url: str) -> GraphQlClient:
    return GraphQlClientFactory(key=test_key, api_url=test_api_url + '/graphql').create()


@pytest.fixture
def url_provider(graphql_client: GraphQlClient) -> UrlProvider:
    return NewOrChangedUrlProvider(
        url_provider=SitemapUrlProvider(
            sitemap_url='https://www.herkesicinguzellik.com/MakaleSiteMap.xml',
            pattern=re.compile(r'^https://www.herkesicinguzellik.com/makale/.*$'),
        ),
        graphql_client=graphql_client
    )


async def callback(url: str) -> None:
    logger.info(f'callback url: {url}')


@pytest.mark.asyncio
async def test_playground(
        client_configuration: wordlift_client.Configuration,
        url_provider: UrlProvider
) -> None:
    embedding_properties = ['http://schema.org/headline', 'http://schema.org/abstract', 'http://schema.org/text']
    embedding_request = EmbeddingRequest(properties=embedding_properties)
    web_page_types = ['http://schema.org/Article']
    concurrency = 5

    async def response_callback(web_page_import_response: WebPageImportResponse) -> None:
        pass

    url_set = set()
    async for url in url_provider.urls():
        url_set.add(url.value)

    @retry(
        # stop=stop_after_attempt(5),  # Retry up to 5 times
        retry=retry_if_exception_type(asyncio.TimeoutError),
        wait=wait_fixed(2),  # Wait 2 seconds between retries
        before=before_log(logger, logging.DEBUG)

    )
    async def web_page_import_callback(url: str) -> None:
        async with wordlift_client.ApiClient(client_configuration) as client:
            api_instance = wordlift_client.WebPagesImportsApi(client)

            request = WebPageImportRequest(
                url=url,
                embedding=embedding_request,
                output_types=web_page_types,
                id_generator="headline-with-url-hash",
            )

            response = await api_instance.create_web_page_imports(
                web_page_import_request=request,
                _request_timeout=60.0
            )
            await response_callback(response)

    delayed = create_delayed(web_page_import_callback, concurrency)
    results = await tqdm.gather(
        *[delayed()(url) for url in list(url_set)],
        total=len(url_set),
        dynamic_ncols=True
    )

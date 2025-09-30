import asyncio
import logging
from datetime import datetime, timedelta

import gql.transport.exceptions
import aiohttp
import pydantic_core
import wordlift_client
from tenacity import (
    retry,
    retry_if_exception_type,
    wait_fixed,
    after_log,
    stop_after_attempt,
)
from wordlift_client import AnalyticsImportRequest

from .url_handler import UrlHandler
from ...graphql.client import GraphQlClient
from ...graphql.utils.query import EntityTopQuery
from ...protocol import Context
from ...url_source import Url

logger = logging.getLogger(__name__)


class SearchConsoleUrlHandler(UrlHandler):
    _context: Context
    _graphql_client: GraphQlClient

    def __init__(self, context: Context, graphql_client: GraphQlClient) -> None:
        self._context = context
        self._graphql_client = graphql_client

    @retry(
        retry=retry_if_exception_type(
            asyncio.TimeoutError
            | aiohttp.client_exceptions.ServerDisconnectedError
            | aiohttp.client_exceptions.ClientConnectorError
            | aiohttp.client_exceptions.ClientPayloadError
            | aiohttp.client_exceptions.ClientConnectorDNSError
            | pydantic_core._pydantic_core.ValidationError
            | wordlift_client.exceptions.ServiceException
            | wordlift_client.exceptions.BadRequestException
            | aiohttp.client_exceptions.ClientOSError
            | gql.transport.exceptions.TransportServerError
        ),
        wait=wait_fixed(2),  # Wait 2 seconds between retries
        stop=stop_after_attempt(3),  # Max 3 retries
        after=after_log(logger, logging.WARNING),
        reraise=True,
    )
    async def __call__(self, url: Url) -> None:
        if not self._context.account.google_search_console_site_url:
            return

        entities = await self._graphql_client.run(
            graphql="entities_top_query", variables={"urls": [url.value]}
        )

        if not entities:
            return

        # Calculate the date 7 days ago from today
        seven_days_ago = datetime.now() - timedelta(days=7)
        entity_top_query = EntityTopQuery.from_graphql_response(entities[0])
        if (
            entity_top_query.top_query_date_created
            and datetime.fromisoformat(entity_top_query.top_query_date_created)
            > seven_days_ago
        ):
            return

        async with wordlift_client.ApiClient(
            self._context.client_configuration
        ) as api_client:
            api_instance = wordlift_client.AnalyticsImportsApi(api_client)
            request = AnalyticsImportRequest(urls=[entity_top_query.url])
            await api_instance.create_analytics_import(request)

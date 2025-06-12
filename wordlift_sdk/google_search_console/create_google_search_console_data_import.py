import logging
from datetime import datetime, timedelta
from typing import Callable, Awaitable

import wordlift_client
from pandas import Series
from tenacity import retry, wait_fixed, stop_after_attempt
from tqdm.asyncio import tqdm
from twisted.mail.scripts.mailmail import Configuration
from wordlift_client import AnalyticsImportRequest

from ..deprecated import create_entities_with_top_query_dataframe
from ..utils import create_delayed

logger = logging.getLogger(__name__)


async def create_google_search_console_data_import(
    configuration: Configuration, key: str, url_list: list[str]
) -> None:
    # Get the entities data with the top query.
    entities_with_top_query_df = await create_entities_with_top_query_dataframe(
        key=key, url_list=url_list
    )

    # Calculate the date 7 days ago from today
    seven_days_ago = datetime.now() - timedelta(days=7)

    # Filter the DataFrame
    entities_with_stale_data_df = entities_with_top_query_df[
        entities_with_top_query_df["top_query_date_created"].isna()
        | (entities_with_top_query_df["top_query_date_created"] < seven_days_ago)
    ]

    import_url_analytics = await import_url_analytics_factory(
        configuration=configuration
    )
    if len(entities_with_stale_data_df) > 0:
        logger.info("Updating missing or stale Google Search Console data...")
        # We're polite and not making more than 2 concurrent reqs.
        delayed = create_delayed(import_url_analytics, 2)
        await tqdm.gather(
            *[delayed(row) for index, row in entities_with_stale_data_df.iterrows()],
            total=len(entities_with_stale_data_df),
        )


async def import_url_analytics_factory(
    configuration: Configuration,
) -> Callable[[Series], Awaitable[None]]:
    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2))
    async def import_url_analytics(row: Series) -> None:
        url = row["url"]
        async with wordlift_client.ApiClient(configuration) as api_client:
            api_instance = wordlift_client.AnalyticsImportsApi(api_client)
            request = AnalyticsImportRequest(urls=[url])
            await api_instance.create_analytics_import(request)

    return import_url_analytics

import logging
from datetime import datetime, timedelta

from pycountry import countries
from tqdm.asyncio import tqdm
from twisted.mail.scripts.mailmail import Configuration
from wordlift_client import AccountInfo

from . import import_url_analytics_factory
from .create_entity_gaps import append_entity_gaps_response_to_row_factory, create_entity_gaps_factory
from ..utils import delayed
from ..utils.create_entities_with_top_query_dataframe import create_entities_with_top_query_dataframe

logger = logging.getLogger(__name__)


async def create_analytics_import(configuration: Configuration, key: str, account: AccountInfo,
                                  url_list: list[str]) -> None:
    # Get the entities data with the top query.
    entities_with_top_query_df = await create_entities_with_top_query_dataframe(key=key, url_list=url_list)

    # Calculate the date 7 days ago from today
    seven_days_ago = datetime.now() - timedelta(days=7)

    # Filter the DataFrame
    entities_with_stale_data_df = entities_with_top_query_df[
        entities_with_top_query_df['top_query_date_created'].isna() | (
                entities_with_top_query_df['top_query_date_created'] < seven_days_ago)
        ]

    import_url_analytics = await import_url_analytics_factory(configuration=configuration)
    if len(entities_with_stale_data_df) > 0:
        logger.info("Updating missing or stale Google Search Console data...")
        # We're polite and not making more than 2 concurrent reqs.
        await tqdm.gather(
            *[delayed(import_url_analytics, 2)(row) for index, row in entities_with_stale_data_df.iterrows()],
            total=len(entities_with_stale_data_df)
        )

        entities_with_top_query_df = await create_entities_with_top_query_dataframe(url_list=url_list)

    country = countries.get(alpha_2=account.country_code.upper())
    await tqdm.gather(
        *[delayed(
            await append_entity_gaps_response_to_row_factory(
                create_entity_gaps=await create_entity_gaps_factory(
                    configuration=configuration,
                    query_location_name=country.name)
            ),
            2
        )(row) for index, row in
          entities_with_top_query_df.iterrows()],
        total=len(entities_with_top_query_df)
    )

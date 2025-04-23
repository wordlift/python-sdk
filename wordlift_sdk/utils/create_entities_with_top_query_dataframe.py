import logging

import pandas as pd
from pandas import DataFrame
from tqdm.asyncio import tqdm

from . import delayed
from ..graphql.utils.query import entity_with_top_query

logger = logging.getLogger(__name__)


async def create_entities_with_top_query_dataframe(url_list: list[str]) -> DataFrame:
    # Get the entities data with the top query.
    logger.info("Loading entities with top query...")
    entities_with_top_query = await tqdm.gather(
        *[delayed(entity_with_top_query, 4)(url) for url in url_list],
        total=len(url_list)
    )

    entities_with_top_query_df = pd.DataFrame(entities_with_top_query)
    entities_with_top_query_df['calc_name'] = entities_with_top_query_df[['name', 'headline', 'title', 'url']].bfill(
        axis=1).iloc[:, 0]
    entities_with_top_query_df['top_query_date_created'] = pd.to_datetime(
        entities_with_top_query_df['top_query_date_created'], errors='coerce')

    return entities_with_top_query_df

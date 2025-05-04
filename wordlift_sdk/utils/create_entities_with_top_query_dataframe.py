import logging

import pandas as pd
from pandas import DataFrame
from tqdm.asyncio import tqdm

from . import delayed
from ..graphql.utils.query import entity_with_top_query_factory

logger = logging.getLogger(__name__)


async def create_entities_with_top_query_dataframe(key: str, url_list: list[str]) -> DataFrame:
    # Get the entities data with the top query.
    logger.info("Loading entities with top query...")
    entity_with_top_query = await entity_with_top_query_factory(key)
    entities_with_top_query = await tqdm.gather(
        *[delayed(entity_with_top_query, 4)(url) for url in url_list],
        total=len(url_list)
    )

    # Get a list of dataframes.
    dataframes = [obj.to_dataframe() for obj in entities_with_top_query if obj is not None]

    # Concat them together, with a new index.
    return pd.concat(dataframes, ignore_index=True)

from typing import Callable, Awaitable, Optional

from pandas import Series, DataFrame
from pycountry import countries
from tqdm.asyncio import tqdm
from twisted.mail.scripts.mailmail import Configuration
from wordlift_client import AccountInfo, AnalysesResponse

from .entity_gaps_callback import entity_gaps_callback_factory
from ...deprecated import create_entities_with_top_query_dataframe
from ...utils import create_delayed


async def create_entity_gaps_factory(
    key: str, configuration: Configuration, account: AccountInfo
):
    async def callback(url_list: list[str]) -> DataFrame:
        # Get the entity data with the top query.
        entities_with_top_query_df = await create_entities_with_top_query_dataframe(
            key=key, url_list=url_list
        )

        country = countries.get(alpha_2=account.country_code.upper())
        delayed = create_delayed(
            await append_entity_gaps_response_to_row_factory(
                entity_gaps_callback=await entity_gaps_callback_factory(
                    configuration=configuration, query_location_name=country.name
                )
            ),
            2,
        )
        series = await tqdm.gather(
            *[delayed(row) for index, row in entities_with_top_query_df.iterrows()],
            total=len(entities_with_top_query_df),
        )

        return DataFrame(series)

    return callback


async def append_entity_gaps_response_to_row_factory(
    entity_gaps_callback: Callable[[Series], Awaitable[Optional[AnalysesResponse]]],
) -> Callable[[Series], Awaitable[Series]]:
    async def append_entity_gaps_response_to_row(row: Series) -> Series:
        response = await entity_gaps_callback(row)
        if response:
            row["entity_gaps"] = response.items
        return row

    return append_entity_gaps_response_to_row

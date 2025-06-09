from dataclasses import asdict
from typing import AsyncGenerator

import pandas as pd

from . import UrlSource, Url
from ..graphql.client import GraphQlClient


class NewOrChangedUrlSource(UrlSource):
    graphql_client: GraphQlClient
    url_provider: UrlSource

    def __init__(self, url_provider: UrlSource, graphql_client: GraphQlClient):
        self.graphql_client = graphql_client
        self.url_provider = url_provider

    async def urls(self) -> AsyncGenerator[Url, None]:
        # Get the list of URLs from the underlying provider.
        url_df = pd.DataFrame([asdict(url) async for url in self.url_provider.urls()])
        # Get the list of URLs from GraphQL.
        list_records = await self.graphql_client.run(
            "entities_url_iri", {"urls": url_df["value"].tolist()}
        )
        graphql_df = pd.DataFrame.from_records(
            data=[record for record in list_records],
            columns=("url", "iri", "date_imported"),
        )
        graphql_df["date_imported"] = pd.to_datetime(
            graphql_df["date_imported"], utc=True, errors="coerce"
        )
        merged_df = pd.merge(
            url_df,
            graphql_df,
            left_on="value",
            right_on="url",
            how="left",
            suffixes=("", "_graphql"),
        )
        filtered_df = merged_df[
            merged_df["date_imported"].isna()
            | (merged_df["date_imported"] < merged_df["date_modified"])
        ]
        for _, row in filtered_df.iterrows():
            yield Url(
                value=row["value"],
                iri=None if pd.isna(row["iri_graphql"]) else row["iri_graphql"],
                date_modified=None
                if pd.isna(row["date_modified"])
                else row["date_modified"],
            )

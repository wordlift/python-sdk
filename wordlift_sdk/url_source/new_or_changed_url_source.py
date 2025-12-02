from dataclasses import asdict
from typing import AsyncGenerator

import pandas as pd

from . import UrlSource, Url
from ..graphql.client import GraphQlClient


class NewOrChangedUrlSource(UrlSource):
    graphql_client: GraphQlClient
    url_provider: UrlSource
    overwrite: bool

    def __init__(
        self, url_provider: UrlSource, graphql_client: GraphQlClient, overwrite: bool
    ):
        self.graphql_client = graphql_client
        self.url_provider = url_provider
        self.overwrite = overwrite

    async def urls(self) -> AsyncGenerator[Url, None]:
        # Get the list of URLs from the underlying provider.
        url_df = pd.DataFrame([asdict(url) async for url in self.url_provider.urls()])
        # Get the list of URLs from GraphQL.
        list_records = await self.graphql_client.run(
            "entities_url_iri_with_source_equal_to_web_page_import",
            {"urls": url_df["value"].tolist() if "value" in url_df.columns else []},
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
            self.overwrite
            | merged_df["date_imported"].isna()
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

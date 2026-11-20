import logging
from dataclasses import asdict
from typing import AsyncGenerator

import pandas as pd

from . import UrlSource, Url
from ..graphql.client import GraphQlClient

logger = logging.getLogger(__name__)


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
        if "value" in url_df.columns:
            # A provider can list a URL more than once (e.g. in two sitemaps).
            url_df = url_df.drop_duplicates(subset="value", keep="first")
        # Get the list of URLs from GraphQL.
        list_records = await self.graphql_client.run(
            "entities_url_iri_with_source_equal_to_web_page_import",
            {"urls": url_df["value"].tolist() if "value" in url_df.columns else []},
        )
        graphql_df = pd.DataFrame.from_records(
            data=[record for record in list_records],
            columns=("url", "iri", "import_hash", "date_imported"),
        )
        graphql_df["date_imported"] = pd.to_datetime(
            graphql_df["date_imported"], utc=True, errors="coerce"
        )
        graphql_df = _one_row_per_url(graphql_df)
        merged_df = pd.merge(
            url_df,
            graphql_df,
            left_on="value",
            right_on="url",
            how="left",
            suffixes=("", "_graphql"),
        )
        merged_df["date_modified"] = pd.to_datetime(
            merged_df["date_modified"], utc=True, errors="coerce"
        )
        # Without a lastmod the stored date proves nothing: keep the URL and
        # let the import hash skip it if it is unchanged.
        filtered_df = merged_df[
            self.overwrite
            | merged_df["date_imported"].isna()
            | merged_df["date_modified"].isna()
            | (merged_df["date_imported"] < merged_df["date_modified"])
        ]
        for _, row in filtered_df.iterrows():
            yield Url(
                value=row["value"],
                iri=None if pd.isna(row["iri_graphql"]) else row["iri_graphql"],
                import_hash=(
                    None
                    if pd.isna(row.get("import_hash_graphql"))
                    else row.get("import_hash_graphql")
                ),
                date_modified=None
                if pd.isna(row["date_modified"])
                else row["date_modified"],
            )


def _one_row_per_url(graphql_df: pd.DataFrame) -> pd.DataFrame:
    """Keep one stored entity per URL so each URL is imported once per run.

    The latest ``date_imported`` wins; ties are broken by the smallest IRI.
    """
    if graphql_df.empty:
        return graphql_df
    iris_per_url = graphql_df.groupby("url")["iri"].nunique()
    shared = int((iris_per_url > 1).sum())
    if shared:
        logger.warning(
            "%d URL(s) have more than one IRI in the graph; importing each once "
            "with the latest imported IRI",
            shared,
        )
    return graphql_df.sort_values(
        ["url", "date_imported", "iri"],
        ascending=[True, False, True],
        na_position="last",
        kind="mergesort",
    ).drop_duplicates(subset="url", keep="first")

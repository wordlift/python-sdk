from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd


@dataclass
class EntityTopQuery:
    iri: str
    url: str
    name: str
    headline: str
    title: str
    top_query_iri: Optional[str] = field(default=None)
    top_query_name: Optional[str] = field(default=None)
    top_query_impressions: Optional[int] = field(default=None)
    top_query_clicks: Optional[int] = field(default=None)
    top_query_date_created: Optional[str] = field(default=None)

    @staticmethod
    def from_graphql_response(entity_data: dict) -> "EntityTopQuery":
        # Initialize top_query fields with default values
        top_query_iri = top_query_name = top_query_impressions = top_query_clicks = top_query_date_created = None

        # Check if there are any top queries
        if entity_data.get('top_query'):
            top_query_data = entity_data['top_query'][0]
            top_query_iri = top_query_data.get('iri')
            top_query_name = top_query_data.get('name')
            top_query_impressions = top_query_data.get('impressions')
            top_query_clicks = top_query_data.get('clicks')
            top_query_date_created = top_query_data.get('date_created')

        # Create an Entity instance
        return EntityTopQuery(
            iri=entity_data['iri'],
            url=entity_data['url'],
            name=entity_data['name'],
            headline=entity_data['headline'],
            title=entity_data['title'],
            top_query_iri=top_query_iri,
            top_query_name=top_query_name,
            top_query_impressions=top_query_impressions,
            top_query_clicks=top_query_clicks,
            top_query_date_created=top_query_date_created
        )

    def to_dataframe(self) -> pd.DataFrame:
        entities_with_top_query_df = pd.DataFrame([asdict(self)])
        entities_with_top_query_df['calc_name'] = entities_with_top_query_df[
                                                      ['name', 'headline', 'title', 'url']].bfill(
            axis=1).iloc[:, 0]
        entities_with_top_query_df['top_query_date_created'] = pd.to_datetime(
            entities_with_top_query_df['top_query_date_created'], errors='coerce')

        return entities_with_top_query_df

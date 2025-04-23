from dataclasses import dataclass, field
from typing import Optional


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

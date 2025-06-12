from typing import Optional, Awaitable, Callable

from tenacity import stop_after_attempt, retry, wait_fixed

from .entity_top_query import EntityTopQuery
from ...client import GraphQlClientFactory


async def entity_with_top_query_factory(
    key: str,
) -> Callable[[str], Awaitable[Optional[EntityTopQuery]]]:
    @retry(stop=stop_after_attempt(5), wait=wait_fixed(2))
    async def entity_with_top_query(url: str) -> Optional[EntityTopQuery]:
        from gql import gql

        # Create a GraphQL client using the defined transport
        client = GraphQlClientFactory(key=key).create_gql_client()

        # Define the GraphQL query
        gql_query = gql("""
            query($url: String!) {
              entities(query: { urlConstraint: { in: [$url] } }) {
                iri
                url: string(name: "schema:url")
                name: string(name: "schema:name")
                headline: string(name: "schema:headline")
                title: string(name: "schema:title")
                top_query: topN(
                  name: "seovoc:hasQuery"
                  sort: { field: "seovoc:impressions3Months", direction: DESC }
                  limit: 1
                ) {
                  iri
                  name: string(name: "seovoc:name")
                  impressions: int(name: "seovoc:impressions3Months")
                  clicks: int(name: "seovoc:clicks3Months")
                  date_created: date(name: "seovoc:dateCreated")
                }
              }
            }
        """)

        # Asynchronous function to execute the query
        async with client as session:
            response = await session.execute(gql_query, variable_values={"url": url})

            if len(response["entities"]) == 0:
                return None

            return EntityTopQuery.from_graphql_response(response["entities"][0])

    return entity_with_top_query

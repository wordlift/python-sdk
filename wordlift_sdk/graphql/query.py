from typing import Dict, Optional, Any

import pandas as pd

from .graphql_client_factory import GraphQLClientFactory


async def query(key: str, query_string: str, root_element: str, columns: list[str],
                variable_values: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    from gql import gql

    # Create a GraphQL client using the defined transport
    client = GraphQLClientFactory(key=key).create()

    # Define the GraphQL query
    gql_query = gql(query_string)

    # Asynchronous function to execute the query
    async with client as session:
        response = await session.execute(gql_query, variable_values=variable_values)
        return pd.DataFrame(response[root_element], columns=columns)

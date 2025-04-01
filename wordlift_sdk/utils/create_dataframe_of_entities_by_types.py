import pandas as pd

from wordlift_sdk import graphql


async def create_dataframe_of_entities_by_types(key: str, types: set[str]) -> pd.DataFrame:
    return await graphql.query(
        key=key,
        query_string="""
            query getEntities($types: [String]!) {
              entities(
                query: { typeConstraint: { in: $types } }
              ) {
                iri
                keywords: string(name: "schema:keywords")
                url: string(name: "schema:url")
              }
            }
        """,
        root_element="entities",
        columns=['iri', 'keywords', 'url'],
        variable_values={
            # `set` cannot be serialized in Python, so we convert to `list`
            "types": list(types)
        }
    )

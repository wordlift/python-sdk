import pandas as pd
from tenacity import retry, stop_after_attempt, wait_fixed

from wordlift_sdk import graphql


@retry(
    stop=stop_after_attempt(5),
    wait=wait_fixed(2)
)
async def create_dataframe_of_entities_with_embedding_vectors(key: str) -> pd.DataFrame:
    return await graphql.query(
        key=key,
        query_string="""
        query {
          entities(
            query: {
              embeddingValueConstraint: { exists: { exists: true, excludeEmpty: true } }
            }
          ) {
            iri
            url: string(name: "schema:url")
          }
        }
    """,
        root_element='entities',
        columns=['iri', 'url'],
    )

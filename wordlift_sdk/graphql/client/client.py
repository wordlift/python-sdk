import os.path
from typing import Any, Optional, Dict, List

from gql import gql
from graphql import parse, OperationDefinitionNode, FieldNode, DocumentNode

from .gql_client_provider import GqlClientProvider


class GraphQlQuery:
    query: DocumentNode
    fields: List[str]

    def __init__(self, query: str):
        self.query = gql(query)
        self.fields = self.extract_field_names(query)

    def get_query(self) -> DocumentNode:
        return self.query

    def get_fields(self) -> List[str]:
        return self.fields

    def extract_field_names(self, query_str):
        parsed = parse(query_str)
        for definition in parsed.definitions:
            if isinstance(definition, OperationDefinitionNode):
                for selection in definition.selection_set.selections:
                    if selection.name.value == "entities":
                        return [
                            field.alias.value if field.alias else field.name.value
                            for field in selection.selection_set.selections
                            if isinstance(field, FieldNode)
                        ]
        return []


file_contents = {}

filenames = [
    "entities_top_query.graphql",
    "entities_url_id.graphql",
    "entities_url_iri.graphql",
    "entities_url_iri_with_source_equal_to_web_page_import.graphql",
]
base_dir = os.path.dirname(os.path.abspath(__file__))

for filename in filenames:
    filepath = os.path.join(base_dir, "../data", filename)
    with open(filepath, "r", encoding="utf-8") as f:
        query = f.read()
        file_contents[filename] = GraphQlQuery(query)


class GraphQlClient:
    _client_provider: GqlClientProvider

    def __init__(self, client_provider: GqlClientProvider):
        self._client_provider = client_provider

    async def run(
        self, graphql: str, variables: Optional[Dict[str, Any]] = None
    ) -> list[dict[str, Any]]:
        query = file_contents[graphql + ".graphql"]

        # Asynchronous function to execute the query
        async with self._client_provider.create() as session:
            response = await session.execute(query.query, variable_values=variables)

            return response["entities"]

"""OOP facade for structured data utilities."""

from __future__ import annotations

from wordlift_sdk.structured_data.constants import DEFAULT_BASE_URL

from .agent_generator import AgentGenerator
from .dataset_resolver import DatasetResolver
from .schema_guide import SchemaGuide
from .yarrrml_pipeline import YarrrmlPipeline


class StructuredDataEngine:
    """OOP facade for structured data utilities."""

    def __init__(
        self,
        dataset: DatasetResolver | None = None,
        schema: SchemaGuide | None = None,
        yarrrml: YarrrmlPipeline | None = None,
        agent: AgentGenerator | None = None,
    ) -> None:
        self.dataset = dataset or DatasetResolver()
        self.schema = schema or SchemaGuide()
        self.yarrrml = yarrrml or YarrrmlPipeline()
        self.agent = agent or AgentGenerator()

    def get_dataset_uri(self, api_key: str, base_url: str = DEFAULT_BASE_URL) -> str:
        return self.dataset.get_dataset_uri(api_key, base_url)

    async def get_dataset_uri_async(
        self, api_key: str, base_url: str = DEFAULT_BASE_URL
    ) -> str:
        return await self.dataset.get_dataset_uri_async(api_key, base_url)

    def generate_from_agent(self, *args, **kwargs):
        return self.agent.generate_from_agent(*args, **kwargs)

    def normalize_yarrrml_mappings(self, *args, **kwargs):
        return self.yarrrml.normalize_mappings(*args, **kwargs)

    def materialize_yarrrml_jsonld(self, *args, **kwargs):
        return self.yarrrml.materialize_jsonld(*args, **kwargs)

    def postprocess_jsonld(self, *args, **kwargs):
        return self.yarrrml.postprocess_jsonld(*args, **kwargs)

    def make_reusable_yarrrml(self, *args, **kwargs):
        return self.yarrrml.make_reusable_yarrrml(*args, **kwargs)

    def ensure_no_blank_nodes(self, *args, **kwargs):
        return self.yarrrml.ensure_no_blank_nodes(*args, **kwargs)

    def build_output_basename(self, *args, **kwargs):
        return self.yarrrml.build_output_basename(*args, **kwargs)

    def shape_specs_for_type(self, *args, **kwargs):
        return self.schema.shape_specs_for_type(*args, **kwargs)

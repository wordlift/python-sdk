"""Structured data workflows and utilities."""

from __future__ import annotations

from .._lazy_exports import resolve_attr

__all__ = [
    "CreateRequest",
    "CreateWorkflow",
    "GenerateRequest",
    "GenerateWorkflow",
    "resolve_api_key_from_context",
    "AgentGenerator",
    "DatasetResolver",
    "SchemaGuide",
    "StructuredDataEngine",
    "StructuredDataOptions",
    "StructuredDataResult",
    "YarrrmlPipeline",
]


_EXPORTS = {
    "CreateRequest": ("wordlift_sdk.structured_data.orchestrator", "CreateRequest"),
    "CreateWorkflow": (
        "wordlift_sdk.structured_data.orchestrator",
        "CreateWorkflow",
    ),
    "GenerateRequest": ("wordlift_sdk.structured_data.orchestrator", "GenerateRequest"),
    "GenerateWorkflow": (
        "wordlift_sdk.structured_data.orchestrator",
        "GenerateWorkflow",
    ),
    "resolve_api_key_from_context": (
        "wordlift_sdk.structured_data.orchestrator",
        "resolve_api_key_from_context",
    ),
    "AgentGenerator": (
        "wordlift_sdk.structured_data.agent_generator",
        "AgentGenerator",
    ),
    "DatasetResolver": (
        "wordlift_sdk.structured_data.dataset_resolver",
        "DatasetResolver",
    ),
    "SchemaGuide": ("wordlift_sdk.structured_data.schema_guide", "SchemaGuide"),
    "StructuredDataEngine": (
        "wordlift_sdk.structured_data.structured_data_engine",
        "StructuredDataEngine",
    ),
    "StructuredDataOptions": (
        "wordlift_sdk.structured_data.engine",
        "StructuredDataOptions",
    ),
    "StructuredDataResult": (
        "wordlift_sdk.structured_data.engine",
        "StructuredDataResult",
    ),
    "YarrrmlPipeline": (
        "wordlift_sdk.structured_data.yarrrml_pipeline",
        "YarrrmlPipeline",
    ),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.structured_data",
        exports=_EXPORTS,
        extra="structured-data",
    )

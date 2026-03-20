from __future__ import annotations

from .._lazy_exports import resolve_attr

__all__ = [
    "ProfileConfig",
    "ProfileConfigError",
    "ProfileDefinition",
    "ProfileMappingRoute",
    "XHTML_PLACEHOLDER",
    "load_profile_config",
    "CloudWorkflowConfig",
    "CloudWorkflowConfigError",
    "get_debug_output_dir",
    "run_cloud_workflow",
    "KgBuildApplicationContainer",
    "IdAllocator",
    "CanonicalIdGenerator",
    "CanonicalIdsPostprocessor",
    "IriLookup",
    "DataFrameUrlIriLookup",
    "KgBuildKpiCollector",
    "DependentRule",
    "IdPolicy",
    "DEFAULT_ID_POLICY",
    "type_name_to_container",
    "GraphPostprocessor",
    "LoadedPostprocessor",
    "PostprocessorContext",
    "load_postprocessors",
    "load_postprocessors_for_profile",
    "ProfileImportProtocol",
    "RmlMappingService",
    "JinjaRdfTemplateReifier",
    "TemplateTextRenderer",
    "YarrrmlValidationIssue",
    "YarrrmlValidationResult",
    "validate_yarrrml_file",
    "validate_yarrrml_paths",
    "validate_yarrrml_text",
]


_EXPORTS: dict[str, tuple[str, str]] = {
    "ProfileConfig": ("wordlift_sdk.kg_build.config", "ProfileConfig"),
    "ProfileConfigError": ("wordlift_sdk.kg_build.config", "ProfileConfigError"),
    "ProfileDefinition": ("wordlift_sdk.kg_build.config", "ProfileDefinition"),
    "ProfileMappingRoute": ("wordlift_sdk.kg_build.config", "ProfileMappingRoute"),
    "XHTML_PLACEHOLDER": ("wordlift_sdk.kg_build.config", "XHTML_PLACEHOLDER"),
    "load_profile_config": ("wordlift_sdk.kg_build.config", "load_profile_config"),
    "CloudWorkflowConfig": ("wordlift_sdk.kg_build.cloud_flow", "CloudWorkflowConfig"),
    "CloudWorkflowConfigError": (
        "wordlift_sdk.kg_build.cloud_flow",
        "CloudWorkflowConfigError",
    ),
    "get_debug_output_dir": (
        "wordlift_sdk.kg_build.cloud_flow",
        "get_debug_output_dir",
    ),
    "run_cloud_workflow": ("wordlift_sdk.kg_build.protocol", "run_cloud_workflow"),
    "KgBuildApplicationContainer": (
        "wordlift_sdk.kg_build.container",
        "KgBuildApplicationContainer",
    ),
    "IdAllocator": (
        "wordlift_sdk.kg_build.postprocessors.processors.id_allocator",
        "IdAllocator",
    ),
    "CanonicalIdGenerator": (
        "wordlift_sdk.kg_build.postprocessors.processors.id_generator",
        "CanonicalIdGenerator",
    ),
    "CanonicalIdsPostprocessor": (
        "wordlift_sdk.kg_build.postprocessors.processors.id_postprocessor",
        "CanonicalIdsPostprocessor",
    ),
    "IriLookup": ("wordlift_sdk.kg_build.iri_lookup", "IriLookup"),
    "DataFrameUrlIriLookup": (
        "wordlift_sdk.kg_build.iri_lookup",
        "DataFrameUrlIriLookup",
    ),
    "KgBuildKpiCollector": ("wordlift_sdk.kg_build.kpi", "KgBuildKpiCollector"),
    "DependentRule": ("wordlift_sdk.kg_build.id_policy", "DependentRule"),
    "IdPolicy": ("wordlift_sdk.kg_build.id_policy", "IdPolicy"),
    "DEFAULT_ID_POLICY": ("wordlift_sdk.kg_build.id_policy", "DEFAULT_ID_POLICY"),
    "type_name_to_container": (
        "wordlift_sdk.kg_build.id_policy",
        "type_name_to_container",
    ),
    "GraphPostprocessor": (
        "wordlift_sdk.kg_build.postprocessors",
        "GraphPostprocessor",
    ),
    "LoadedPostprocessor": (
        "wordlift_sdk.kg_build.postprocessors",
        "LoadedPostprocessor",
    ),
    "PostprocessorContext": (
        "wordlift_sdk.kg_build.postprocessors",
        "PostprocessorContext",
    ),
    "load_postprocessors": (
        "wordlift_sdk.kg_build.postprocessors",
        "load_postprocessors",
    ),
    "load_postprocessors_for_profile": (
        "wordlift_sdk.kg_build.postprocessors",
        "load_postprocessors_for_profile",
    ),
    "ProfileImportProtocol": (
        "wordlift_sdk.kg_build.protocol",
        "ProfileImportProtocol",
    ),
    "RmlMappingService": ("wordlift_sdk.kg_build.rml_mapping", "RmlMappingService"),
    "JinjaRdfTemplateReifier": (
        "wordlift_sdk.kg_build.templates",
        "JinjaRdfTemplateReifier",
    ),
    "TemplateTextRenderer": ("wordlift_sdk.kg_build.templates", "TemplateTextRenderer"),
    "YarrrmlValidationIssue": (
        "wordlift_sdk.kg_build.yarrrml_validator",
        "YarrrmlValidationIssue",
    ),
    "YarrrmlValidationResult": (
        "wordlift_sdk.kg_build.yarrrml_validator",
        "YarrrmlValidationResult",
    ),
    "validate_yarrrml_file": (
        "wordlift_sdk.kg_build.yarrrml_validator",
        "validate_yarrrml_file",
    ),
    "validate_yarrrml_paths": (
        "wordlift_sdk.kg_build.yarrrml_validator",
        "validate_yarrrml_paths",
    ),
    "validate_yarrrml_text": (
        "wordlift_sdk.kg_build.yarrrml_validator",
        "validate_yarrrml_text",
    ),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.kg_build",
        exports=_EXPORTS,
        extra="kg-build",
    )

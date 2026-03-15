from .._lazy_exports import resolve_attr

__all__ = [
    "AdapterRegistry",
    "IngestionConfigError",
    "IngestionError",
    "IngestionOrchestrator",
    "IngestionResult",
    "IngestionWarning",
    "LoadedPage",
    "LoaderAdapter",
    "LoaderConfigError",
    "LoaderRuntimeError",
    "ResolvedIngestionConfig",
    "SourceAdapter",
    "SourceConfigError",
    "SourceItem",
    "SourceRuntimeError",
    "create_loader_registry",
    "create_orchestrator",
    "create_structured_data_inventory_from_ingestion",
    "create_source_registry",
    "create_type_classification_csv_from_ingestion",
    "SourceResolutionResult",
    "resolve_ingestion_source_items",
    "run_ingestion",
    "resolve_ingestion_config_from_getter",
    "resolve_ingestion_config_from_mapping",
    "resolve_ingestion_config_from_provider",
    "StructuredDataInventoryRow",
]


_EXPORTS = {
    "AdapterRegistry": ("wordlift_sdk.ingestion.registry", "AdapterRegistry"),
    "IngestionConfigError": ("wordlift_sdk.ingestion.errors", "IngestionConfigError"),
    "IngestionError": ("wordlift_sdk.ingestion.errors", "IngestionError"),
    "IngestionOrchestrator": (
        "wordlift_sdk.ingestion.orchestrator",
        "IngestionOrchestrator",
    ),
    "IngestionResult": ("wordlift_sdk.ingestion.orchestrator", "IngestionResult"),
    "IngestionWarning": ("wordlift_sdk.ingestion.events", "IngestionWarning"),
    "LoadedPage": ("wordlift_sdk.ingestion.models", "LoadedPage"),
    "LoaderAdapter": ("wordlift_sdk.ingestion.protocols", "LoaderAdapter"),
    "LoaderConfigError": ("wordlift_sdk.ingestion.errors", "LoaderConfigError"),
    "LoaderRuntimeError": ("wordlift_sdk.ingestion.errors", "LoaderRuntimeError"),
    "ResolvedIngestionConfig": (
        "wordlift_sdk.ingestion.resolver",
        "ResolvedIngestionConfig",
    ),
    "SourceAdapter": ("wordlift_sdk.ingestion.protocols", "SourceAdapter"),
    "SourceConfigError": ("wordlift_sdk.ingestion.errors", "SourceConfigError"),
    "SourceItem": ("wordlift_sdk.ingestion.models", "SourceItem"),
    "SourceRuntimeError": ("wordlift_sdk.ingestion.errors", "SourceRuntimeError"),
    "create_loader_registry": (
        "wordlift_sdk.ingestion.factory",
        "create_loader_registry",
    ),
    "create_orchestrator": ("wordlift_sdk.ingestion.factory", "create_orchestrator"),
    "create_structured_data_inventory_from_ingestion": (
        "wordlift_sdk.ingestion.inventory",
        "create_structured_data_inventory_from_ingestion",
    ),
    "create_source_registry": (
        "wordlift_sdk.ingestion.factory",
        "create_source_registry",
    ),
    "create_type_classification_csv_from_ingestion": (
        "wordlift_sdk.ingestion.type_classification",
        "create_type_classification_csv_from_ingestion",
    ),
    "SourceResolutionResult": (
        "wordlift_sdk.ingestion.api",
        "SourceResolutionResult",
    ),
    "resolve_ingestion_source_items": (
        "wordlift_sdk.ingestion.api",
        "resolve_ingestion_source_items",
    ),
    "run_ingestion": ("wordlift_sdk.ingestion.api", "run_ingestion"),
    "resolve_ingestion_config_from_getter": (
        "wordlift_sdk.ingestion.resolver",
        "resolve_ingestion_config_from_getter",
    ),
    "resolve_ingestion_config_from_mapping": (
        "wordlift_sdk.ingestion.resolver",
        "resolve_ingestion_config_from_mapping",
    ),
    "resolve_ingestion_config_from_provider": (
        "wordlift_sdk.ingestion.resolver",
        "resolve_ingestion_config_from_provider",
    ),
    "StructuredDataInventoryRow": (
        "wordlift_sdk.ingestion.inventory",
        "StructuredDataInventoryRow",
    ),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.ingestion",
        exports=_EXPORTS,
        extra="ingestion",
    )

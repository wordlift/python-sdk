from ._lazy_exports import resolve_attr

__all__ = ["run_kg_import_workflow", "kg_build", "ingestion"]


_EXPORTS = {
    "run_kg_import_workflow": ("wordlift_sdk.main", "run_kg_import_workflow"),
    "kg_build": ("wordlift_sdk.kg_build", None),
    "ingestion": ("wordlift_sdk.ingestion", None),
}


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'wordlift_sdk' has no attribute '{name}'")

    target_module, attr_name = target
    if attr_name is None:
        return __import__(target_module, fromlist=["*"])

    return resolve_attr(
        name=name,
        module_name="wordlift_sdk",
        exports={name: (target_module, attr_name)},
        extra="workflow" if name == "run_kg_import_workflow" else None,
    )

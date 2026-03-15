from .._lazy_exports import resolve_attr

__all__ = ["KgImportWorkflow"]


_EXPORTS = {
    "KgImportWorkflow": (
        "wordlift_sdk.workflow.kg_import_workflow",
        "KgImportWorkflow",
    )
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.workflow",
        exports=_EXPORTS,
        extra="workflow",
    )

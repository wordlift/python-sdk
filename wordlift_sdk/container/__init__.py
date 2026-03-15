from .._lazy_exports import resolve_attr

__all__ = ["ApplicationContainer"]


_EXPORTS = {
    "ApplicationContainer": (
        "wordlift_sdk.container.application_container",
        "ApplicationContainer",
    )
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.container",
        exports=_EXPORTS,
        extra="workflow",
    )

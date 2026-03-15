from .._lazy_exports import resolve_attr

__all__ = ["create_internal_link_handler"]


_EXPORTS = {
    "create_internal_link_handler": (
        "wordlift_sdk.internal_link.utils",
        "create_internal_link_handler",
    )
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.internal_link",
        exports=_EXPORTS,
        extra="legacy",
    )

from .._lazy_exports import resolve_attr

__all__ = ["create_entities_with_top_query_dataframe"]


_EXPORTS = {
    "create_entities_with_top_query_dataframe": (
        "wordlift_sdk.deprecated.create_entities_with_top_query_dataframe",
        "create_entities_with_top_query_dataframe",
    )
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.deprecated",
        exports=_EXPORTS,
        extra="legacy",
    )

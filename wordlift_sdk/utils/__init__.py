from .._lazy_exports import resolve_attr

__all__ = [
    "create_dataframe_from_google_sheets",
    "create_dataframe_of_entities_by_types",
    "create_dataframe_of_entities_with_embedding_vectors",
    "create_dataframe_of_url_iri",
    "create_entity_patch_request",
    "create_delayed",
    "get_me",
    "reset_me",
    "HtmlConverter",
    "AutoConcurrencyController",
]


_EXPORTS = {
    "create_dataframe_from_google_sheets": (
        "wordlift_sdk.utils.create_dataframe_from_google_sheets",
        "create_dataframe_from_google_sheets",
    ),
    "create_dataframe_of_entities_by_types": (
        "wordlift_sdk.utils.create_dataframe_of_entities_by_types",
        "create_dataframe_of_entities_by_types",
    ),
    "create_dataframe_of_entities_with_embedding_vectors": (
        "wordlift_sdk.utils.create_dataframe_of_entities_with_embedding_vectors",
        "create_dataframe_of_entities_with_embedding_vectors",
    ),
    "create_dataframe_of_url_iri": (
        "wordlift_sdk.utils.create_dataframe_of_url_iri",
        "create_dataframe_of_url_iri",
    ),
    "create_entity_patch_request": (
        "wordlift_sdk.utils.create_entity_patch_request",
        "create_entity_patch_request",
    ),
    "create_delayed": ("wordlift_sdk.utils.delayed", "create_delayed"),
    "get_me": ("wordlift_sdk.utils.get_me", "get_me"),
    "reset_me": ("wordlift_sdk.utils.reset_me", "reset_me"),
    "HtmlConverter": ("wordlift_sdk.utils.html_converter", "HtmlConverter"),
    "AutoConcurrencyController": (
        "wordlift_sdk.utils.auto_concurrency",
        "AutoConcurrencyController",
    ),
}


def __getattr__(name: str):
    extra = {
        "create_dataframe_from_google_sheets": "google-sheets",
        "HtmlConverter": "render",
    }.get(name, "legacy")
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.utils",
        exports=_EXPORTS,
        extra=extra,
    )

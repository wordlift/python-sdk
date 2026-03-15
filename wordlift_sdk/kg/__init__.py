from .._lazy_exports import resolve_attr

__all__ = ["Entity", "EntityStore", "EntityStoreFactory"]


_EXPORTS = {
    "Entity": ("wordlift_sdk.kg.entity", "Entity"),
    "EntityStore": ("wordlift_sdk.kg.entity_store", "EntityStore"),
    "EntityStoreFactory": (
        "wordlift_sdk.kg.entity_store_factory",
        "EntityStoreFactory",
    ),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.kg",
        exports=_EXPORTS,
        extra="legacy",
    )

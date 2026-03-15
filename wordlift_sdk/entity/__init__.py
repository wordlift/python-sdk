from .._lazy_exports import resolve_attr

__all__ = ["enrich", "ParseHtmlCallback", "patch"]


_EXPORTS = {
    "enrich": ("wordlift_sdk.entity.enrich", "enrich"),
    "ParseHtmlCallback": ("wordlift_sdk.entity.enrich", "ParseHtmlCallback"),
    "patch": ("wordlift_sdk.entity.patch", "patch"),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.entity",
        exports=_EXPORTS,
        extra="legacy",
    )

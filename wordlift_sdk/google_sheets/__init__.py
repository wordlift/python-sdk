from .._lazy_exports import resolve_attr

__all__ = ["GoogleSheetsLookup"]


_EXPORTS = {
    "GoogleSheetsLookup": (
        "wordlift_sdk.google_sheets.google_sheets_lookup",
        "GoogleSheetsLookup",
    )
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.google_sheets",
        exports=_EXPORTS,
        extra="google-sheets",
    )

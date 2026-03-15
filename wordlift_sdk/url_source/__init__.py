from .._lazy_exports import resolve_attr

__all__ = [
    "Url",
    "UrlSource",
    "GoogleSheetsUrlSource",
    "ListUrlSource",
    "SitemapUrlSource",
]


_EXPORTS = {
    "Url": ("wordlift_sdk.url_source.url_source", "Url"),
    "UrlSource": ("wordlift_sdk.url_source.url_source", "UrlSource"),
    "GoogleSheetsUrlSource": (
        "wordlift_sdk.url_source.google_sheets_url_source",
        "GoogleSheetsUrlSource",
    ),
    "ListUrlSource": ("wordlift_sdk.url_source.list_url_source", "ListUrlSource"),
    "SitemapUrlSource": (
        "wordlift_sdk.url_source.sitemap_url_source",
        "SitemapUrlSource",
    ),
}


def __getattr__(name: str):
    extra = "google-sheets" if name == "GoogleSheetsUrlSource" else "ingestion"
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.url_source",
        exports=_EXPORTS,
        extra=extra,
    )

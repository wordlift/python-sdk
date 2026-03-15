from .._lazy_exports import resolve_attr

__all__ = [
    "create_google_search_console_data_import",
    "import_url_analytics_factory",
    "raise_error_if_account_analytics_not_configured",
    "create_canonical_csv_from_gsc_impressions",
    "load_service_account_credentials",
    "load_authorized_user_credentials",
    "parse_interval_to_date_range",
]


_EXPORTS = {
    "create_google_search_console_data_import": (
        "wordlift_sdk.google_search_console.create_google_search_console_data_import",
        "create_google_search_console_data_import",
    ),
    "import_url_analytics_factory": (
        "wordlift_sdk.google_search_console.create_google_search_console_data_import",
        "import_url_analytics_factory",
    ),
    "raise_error_if_account_analytics_not_configured": (
        "wordlift_sdk.google_search_console.raise_error_if_account_analytics_not_configured",
        "raise_error_if_account_analytics_not_configured",
    ),
    "create_canonical_csv_from_gsc_impressions": (
        "wordlift_sdk.google_search_console.canonical_selection",
        "create_canonical_csv_from_gsc_impressions",
    ),
    "load_service_account_credentials": (
        "wordlift_sdk.google_search_console.canonical_selection",
        "load_service_account_credentials",
    ),
    "load_authorized_user_credentials": (
        "wordlift_sdk.google_search_console.canonical_selection",
        "load_authorized_user_credentials",
    ),
    "parse_interval_to_date_range": (
        "wordlift_sdk.google_search_console.canonical_selection",
        "parse_interval_to_date_range",
    ),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.google_search_console",
        exports=_EXPORTS,
        extra="google-search-console",
    )

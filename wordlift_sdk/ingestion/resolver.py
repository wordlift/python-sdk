from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from wordlift_sdk.client.client_configuration_factory import ClientConfigurationFactory

from .errors import IngestionConfigError, SourceConfigError
from .events import IngestionWarning


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError(f"Cannot parse int from {type(value)}")


def _normalize_loader_name(value: str) -> str:
    key = value.strip().lower().replace("-", "_")
    return {
        "web_scrape_api": "web_scrape_api",
        "webscrapeapi": "web_scrape_api",
        "default": "web_scrape_api",
        "simple": "simple",
        "proxy": "proxy",
        "playwright": "playwright",
        "premium_scraper": "premium_scraper",
        "passthrough": "passthrough",
        "auto": "auto",
    }.get(key, key)


def _normalize_source_name(value: str) -> str:
    key = value.strip().lower().replace("_", "-")
    mapped = {
        "urls": "urls",
        "sitemap": "sitemap",
        "sheets": "sheets",
        "local": "local",
        "debug-cloud": "local",
        "auto": "auto",
    }.get(key, key)
    return mapped


@dataclass(frozen=True)
class ResolvedIngestionConfig:
    source_name: str
    loader_name: str
    passthrough_when_html: bool
    timeout_ms: int
    retry_attempts: int
    retry_backoff_ms: int
    source_config: dict[str, Any] = field(default_factory=dict)
    loader_config: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[IngestionWarning, ...] = field(default_factory=tuple)


def _get_from_mapping(mapping: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return mapping.get(key, default)


def _build_source_config(
    source_name: str,
    get_value: Callable[[str, Any], Any],
) -> dict[str, Any]:
    if source_name == "urls":
        urls = get_value("URLS")
        if urls is None:
            raise SourceConfigError(
                "URLS is required for INGEST_SOURCE=urls",
                code="INGEST_CFG_MISSING_SOURCE",
            )
        return {"urls": urls}

    if source_name == "sitemap":
        sitemap_url = get_value("SITEMAP_URL")
        if not sitemap_url:
            raise SourceConfigError(
                "SITEMAP_URL is required for INGEST_SOURCE=sitemap",
                code="INGEST_CFG_MISSING_SOURCE",
            )
        return {
            "sitemap_url": sitemap_url,
            "sitemap_url_pattern": get_value("SITEMAP_URL_PATTERN"),
        }

    if source_name == "sheets":
        sheets_url = get_value("SHEETS_URL")
        sheets_name = get_value("SHEETS_NAME")
        sheets_service_account = get_value("SHEETS_SERVICE_ACCOUNT")
        missing = [
            key
            for key, value in {
                "SHEETS_URL": sheets_url,
                "SHEETS_NAME": sheets_name,
                "SHEETS_SERVICE_ACCOUNT": sheets_service_account,
            }.items()
            if not value
        ]
        if missing:
            raise SourceConfigError(
                "Incomplete sheets configuration",
                code="INGEST_SRC_SHEETS_CONFIG_INVALID",
                details={"missing_keys": missing},
            )
        return {
            "sheets_url": sheets_url,
            "sheets_name": sheets_name,
            "sheets_service_account": sheets_service_account,
        }

    if source_name == "local":
        return {
            "items": get_value("INGEST_LOCAL_ITEMS", get_value("DEBUG_CLOUD_ITEMS")),
            "file": get_value("INGEST_LOCAL_FILE", get_value("DEBUG_CLOUD_FILE")),
        }

    raise IngestionConfigError(
        f"Unsupported source '{source_name}'",
        code="INGEST_CFG_UNSUPPORTED_SOURCE",
    )


def _resolve_legacy_source(
    get_value: Callable[[str, Any], Any],
) -> tuple[str, list[str]]:
    candidates: list[str] = []

    urls = get_value("URLS")
    if urls:
        candidates.append("urls")

    sitemap_url = get_value("SITEMAP_URL")
    if sitemap_url:
        candidates.append("sitemap")

    sheets_url = get_value("SHEETS_URL")
    sheets_name = get_value("SHEETS_NAME")
    sheets_service_account = get_value("SHEETS_SERVICE_ACCOUNT")
    if sheets_url or sheets_name or sheets_service_account:
        if not (sheets_url and sheets_name and sheets_service_account):
            raise SourceConfigError(
                "Incomplete sheets configuration",
                code="INGEST_SRC_SHEETS_CONFIG_INVALID",
                details={
                    "required": [
                        "SHEETS_URL",
                        "SHEETS_NAME",
                        "SHEETS_SERVICE_ACCOUNT",
                    ]
                },
            )
        candidates.append("sheets")

    local_items = get_value("INGEST_LOCAL_ITEMS", get_value("DEBUG_CLOUD_ITEMS"))
    local_file = get_value("INGEST_LOCAL_FILE", get_value("DEBUG_CLOUD_FILE"))
    if local_items or local_file:
        candidates.append("local")

    if not candidates:
        raise IngestionConfigError(
            "No source configured",
            code="INGEST_CFG_MISSING_SOURCE",
        )

    priority = ["urls", "sitemap", "sheets", "local"]
    for name in priority:
        if name in candidates:
            return name, candidates

    raise IngestionConfigError(
        "Unable to resolve source",
        code="INGEST_CFG_MISSING_SOURCE",
    )


def _create_client_configuration(get_value: Callable[[str, Any], Any]) -> Any | None:
    key = get_value("WORDLIFT_KEY")
    if not key:
        return None
    api_url = get_value("API_URL", "https://api.wordlift.io")
    ssl_ca_cert = get_value("SSL_CA_CERT", None)
    return ClientConfigurationFactory(
        key=key,
        api_url=api_url,
        ssl_ca_cert=ssl_ca_cert,
    ).create()


def resolve_ingestion_config_from_getter(
    get_value: Callable[[str, Any], Any],
) -> ResolvedIngestionConfig:
    warnings: list[IngestionWarning] = []

    ingest_source_raw = get_value("INGEST_SOURCE")
    ingest_loader_raw = get_value("INGEST_LOADER")

    ingest_source = (
        _normalize_source_name(str(ingest_source_raw))
        if ingest_source_raw is not None
        else None
    )
    ingest_loader = (
        _normalize_loader_name(str(ingest_loader_raw))
        if ingest_loader_raw is not None
        else None
    )

    legacy_mode = get_value("WEB_PAGE_IMPORT_MODE")
    legacy_loader = (
        _normalize_loader_name(str(legacy_mode)) if legacy_mode is not None else None
    )

    if ingest_source not in {None, "auto"}:
        source_name = ingest_source
        _resolve_legacy_source_errors_only(get_value)
        legacy_source_name, _legacy_candidates = _resolve_legacy_source_if_present(
            get_value
        )
        if legacy_source_name and legacy_source_name != source_name:
            warnings.append(
                IngestionWarning(
                    code="INGEST_CFG_CONFLICT",
                    message="New source key overrides legacy source settings.",
                    new_key="INGEST_SOURCE",
                    new_value=source_name,
                    legacy_key="legacy_source",
                    legacy_value=legacy_source_name,
                    winner="INGEST_SOURCE",
                )
            )
    else:
        source_name, legacy_candidates = _resolve_legacy_source(get_value)
        if len(legacy_candidates) > 1:
            warnings.append(
                IngestionWarning(
                    code="INGEST_CFG_MULTIPLE_LEGACY_SOURCES",
                    message="Multiple legacy sources are set; deterministic priority applied.",
                    winner=source_name,
                    details={"candidates": legacy_candidates},
                )
            )

    if ingest_loader not in {None, "auto"}:
        loader_name = ingest_loader
        if legacy_loader and legacy_loader != loader_name:
            warnings.append(
                IngestionWarning(
                    code="INGEST_CFG_CONFLICT",
                    message="New loader key overrides legacy loader settings.",
                    new_key="INGEST_LOADER",
                    new_value=loader_name,
                    legacy_key="WEB_PAGE_IMPORT_MODE",
                    legacy_value=legacy_mode,
                    winner="INGEST_LOADER",
                )
            )
    else:
        loader_name = legacy_loader or "web_scrape_api"

    if loader_name == "auto":
        loader_name = "web_scrape_api"

    if loader_name not in {
        "simple",
        "proxy",
        "playwright",
        "premium_scraper",
        "web_scrape_api",
        "passthrough",
    }:
        raise IngestionConfigError(
            f"Unsupported loader '{loader_name}'",
            code="INGEST_CFG_UNSUPPORTED_LOADER",
        )

    passthrough_when_html = _parse_bool(
        get_value("INGEST_PASSTHROUGH_WHEN_HTML"), default=True
    )
    timeout_ms = _parse_int(
        get_value("INGEST_TIMEOUT_MS", get_value("WEB_PAGE_IMPORT_TIMEOUT")),
        default=30000,
    )
    retry_attempts = _parse_int(get_value("INGEST_RETRY_ATTEMPTS"), default=5)
    retry_backoff_ms = _parse_int(get_value("INGEST_RETRY_BACKOFF_MS"), default=2000)

    _validate_loader_option_combinations(loader_name, get_value)

    source_config = _build_source_config(source_name, get_value)

    loader_config = {
        "timeout_ms": timeout_ms,
        "retry_attempts": retry_attempts,
        "retry_backoff_ms": retry_backoff_ms,
        "client_configuration": _create_client_configuration(get_value),
        "render_js": get_value("WEB_PAGE_IMPORT_RENDER_JS"),
        "wait_for": get_value("WEB_PAGE_IMPORT_WAIT_FOR"),
        "country_code": get_value("WEB_PAGE_IMPORT_COUNTRY_CODE"),
        "premium_proxy": get_value("WEB_PAGE_IMPORT_PREMIUM_PROXY"),
        "block_ads": get_value("WEB_PAGE_IMPORT_BLOCK_ADS"),
        "wait_until": get_value("PLAYWRIGHT_WAIT_UNTIL", "networkidle"),
        "headless": _parse_bool(get_value("PLAYWRIGHT_HEADLESS"), default=True),
    }

    return ResolvedIngestionConfig(
        source_name=source_name,
        loader_name=loader_name,
        passthrough_when_html=passthrough_when_html,
        timeout_ms=timeout_ms,
        retry_attempts=retry_attempts,
        retry_backoff_ms=retry_backoff_ms,
        source_config=source_config,
        loader_config=loader_config,
        warnings=tuple(warnings),
    )


def resolve_ingestion_config_from_mapping(
    settings: Mapping[str, Any],
) -> ResolvedIngestionConfig:
    return resolve_ingestion_config_from_getter(
        lambda key, default=None: _get_from_mapping(settings, key, default)
    )


def resolve_ingestion_config_from_provider(provider: Any) -> ResolvedIngestionConfig:
    return resolve_ingestion_config_from_getter(provider.get_value)


def _resolve_legacy_source_if_present(
    get_value: Callable[[str, Any], Any],
) -> tuple[str | None, list[str]]:
    try:
        name, candidates = _resolve_legacy_source(get_value)
        return name, candidates
    except IngestionConfigError:
        return None, []


def _resolve_legacy_source_errors_only(get_value: Callable[[str, Any], Any]) -> None:
    sheets_url = get_value("SHEETS_URL")
    sheets_name = get_value("SHEETS_NAME")
    sheets_service_account = get_value("SHEETS_SERVICE_ACCOUNT")
    if sheets_url or sheets_name or sheets_service_account:
        if not (sheets_url and sheets_name and sheets_service_account):
            raise SourceConfigError(
                "Incomplete sheets configuration",
                code="INGEST_SRC_SHEETS_CONFIG_INVALID",
                details={
                    "required": [
                        "SHEETS_URL",
                        "SHEETS_NAME",
                        "SHEETS_SERVICE_ACCOUNT",
                    ]
                },
            )


def _validate_loader_option_combinations(
    loader_name: str, get_value: Callable[[str, Any], Any]
) -> None:
    premium_only = {
        "WEB_PAGE_IMPORT_RENDER_JS": get_value("WEB_PAGE_IMPORT_RENDER_JS"),
        "WEB_PAGE_IMPORT_WAIT_FOR": get_value("WEB_PAGE_IMPORT_WAIT_FOR"),
        "WEB_PAGE_IMPORT_COUNTRY_CODE": get_value("WEB_PAGE_IMPORT_COUNTRY_CODE"),
        "WEB_PAGE_IMPORT_PREMIUM_PROXY": get_value("WEB_PAGE_IMPORT_PREMIUM_PROXY"),
        "WEB_PAGE_IMPORT_BLOCK_ADS": get_value("WEB_PAGE_IMPORT_BLOCK_ADS"),
    }
    if loader_name == "premium_scraper":
        return

    active = {
        key: value
        for key, value in premium_only.items()
        if value not in (None, "", False, "false", "False", 0)
    }
    if active:
        raise IngestionConfigError(
            "Premium scraper options require premium_scraper loader",
            code="INGEST_CFG_INVALID_OPTION_COMBINATION",
            details={"active_options": sorted(active.keys()), "loader": loader_name},
        )


__all__ = [
    "ResolvedIngestionConfig",
    "resolve_ingestion_config_from_getter",
    "resolve_ingestion_config_from_mapping",
    "resolve_ingestion_config_from_provider",
]

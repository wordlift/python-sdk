from __future__ import annotations

import pytest

from wordlift_sdk.ingestion.errors import IngestionConfigError, SourceConfigError
from wordlift_sdk.ingestion.resolver import (
    DEFAULT_CRAWLER_TIMEOUT_MS,
    resolve_ingestion_config_from_mapping,
)


def test_missing_ingest_source_fails_fast() -> None:
    with pytest.raises(IngestionConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_LOADER": "web_scrape_api",
                "URLS": ["https://example.com"],
            }
        )
    assert exc.value.code == "INGEST_CFG_MISSING_SOURCE"


def test_missing_ingest_loader_fails_fast() -> None:
    with pytest.raises(IngestionConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_SOURCE": "urls",
                "URLS": ["https://example.com"],
            }
        )
    assert exc.value.code == "INGEST_CFG_MISSING_LOADER"


def test_loader_defaults_are_explicit_and_no_legacy_warnings() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com"],
        }
    )
    assert cfg.loader_name == "web_scrape_api"
    assert cfg.warnings == ()
    assert cfg.timeout_ms == 30000
    assert cfg.loader_config["wait_until"] == "domcontentloaded"


def test_incomplete_sheets_fails_fast() -> None:
    with pytest.raises(SourceConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_SOURCE": "sheets",
                "INGEST_LOADER": "web_scrape_api",
                "SHEETS_URL": "https://docs.google.com/spreadsheets/d/123",
                "SHEETS_NAME": "Sheet1",
            }
        )
    assert exc.value.code == "INGEST_SRC_SHEETS_CONFIG_INVALID"


def test_premium_options_require_premium_loader() -> None:
    with pytest.raises(IngestionConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_SOURCE": "urls",
                "INGEST_LOADER": "proxy",
                "URLS": ["https://example.com"],
                "WEB_PAGE_IMPORT_RENDER_JS": True,
            }
        )
    assert exc.value.code == "INGEST_CFG_INVALID_OPTION_COMBINATION"


def test_url_regex_is_resolved_and_validated() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com"],
            "URL_REGEX": r"/article/",
        }
    )
    assert cfg.url_regex == r"/article/"

    with pytest.raises(IngestionConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_SOURCE": "urls",
                "INGEST_LOADER": "web_scrape_api",
                "URLS": ["https://example.com"],
                "URL_REGEX": r"([",
            }
        )
    assert exc.value.code == "INGEST_CFG_INVALID_URL_REGEX"


def test_crawler_loader_is_accepted() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "crawler",
            "URLS": ["https://example.com"],
        }
    )
    assert cfg.loader_name == "crawler"
    assert cfg.warnings == ()


def test_crawler_env_vars_are_passed_to_loader_config() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "crawler",
            "URLS": ["https://example.com"],
            "CRAWLER_JS_RENDER_MODE": "auto",
            "CRAWLER_PROXY_MODE": "standard",
        }
    )
    assert cfg.loader_config["crawler_js_render_mode"] == "auto"
    assert cfg.loader_config["crawler_proxy_mode"] == "standard"


def test_crawler_env_vars_default_to_none_when_absent() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "crawler",
            "URLS": ["https://example.com"],
        }
    )
    assert cfg.loader_config["crawler_js_render_mode"] is None
    assert cfg.loader_config["crawler_proxy_mode"] is None


def test_crawler_loader_defaults_timeout_to_ten_minutes() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "crawler",
            "URLS": ["https://example.com"],
        }
    )
    assert cfg.timeout_ms == DEFAULT_CRAWLER_TIMEOUT_MS
    assert DEFAULT_CRAWLER_TIMEOUT_MS == 600_000


def test_crawler_loader_explicit_timeout_overrides_default() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "crawler",
            "URLS": ["https://example.com"],
            "INGEST_TIMEOUT_MS": 30000,
        }
    )
    assert cfg.timeout_ms == 30000


def test_non_crawler_loader_keeps_thirty_second_default() -> None:
    from wordlift_sdk.render.render_options import DEFAULT_PLAYWRIGHT_TIMEOUT_MS

    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com"],
        }
    )
    assert cfg.timeout_ms == DEFAULT_PLAYWRIGHT_TIMEOUT_MS


def test_sitemap_url_pattern_is_deprecated_alias_for_url_regex() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "sitemap",
            "INGEST_LOADER": "web_scrape_api",
            "SITEMAP_URL": "https://example.com/sitemap.xml",
            "SITEMAP_URL_PATTERN": r"/article/",
        }
    )
    assert cfg.url_regex == r"/article/"
    assert len(cfg.warnings) == 1
    assert cfg.warnings[0].code == "INGEST_CFG_DEPRECATED_OPTION"

    cfg2 = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "sitemap",
            "INGEST_LOADER": "web_scrape_api",
            "SITEMAP_URL": "https://example.com/sitemap.xml",
            "SITEMAP_URL_PATTERN": r"/legacy/",
            "URL_REGEX": r"/new/",
        }
    )
    assert cfg2.url_regex == r"/new/"
    assert len(cfg2.warnings) == 1
    assert cfg2.warnings[0].winner == "URL_REGEX"

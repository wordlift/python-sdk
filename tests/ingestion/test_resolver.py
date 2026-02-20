from __future__ import annotations

import pytest

from wordlift_sdk.ingestion.errors import IngestionConfigError, SourceConfigError
from wordlift_sdk.ingestion.resolver import resolve_ingestion_config_from_mapping


def test_ingest_loader_wins_over_legacy_with_structured_warning() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "URLS": ["https://example.com"],
            "INGEST_LOADER": "simple",
            "WEB_PAGE_IMPORT_MODE": "premium_scraper",
        }
    )
    assert cfg.loader_name == "simple"
    assert len(cfg.warnings) == 1
    warning = cfg.warnings[0]
    assert warning.code == "INGEST_CFG_CONFLICT"
    assert warning.new_key == "INGEST_LOADER"
    assert warning.legacy_key == "WEB_PAGE_IMPORT_MODE"
    assert warning.winner == "INGEST_LOADER"


def test_legacy_default_maps_to_web_scrape_api() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "URLS": ["https://example.com"],
            "WEB_PAGE_IMPORT_MODE": "default",
        }
    )
    assert cfg.loader_name == "web_scrape_api"


@pytest.mark.parametrize(
    ("legacy_mode", "expected"),
    [
        ("default", "web_scrape_api"),
        ("proxy", "proxy"),
        ("premium_scraper", "premium_scraper"),
    ],
)
def test_legacy_loader_mapping_compatibility(legacy_mode: str, expected: str) -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "URLS": ["https://example.com"],
            "WEB_PAGE_IMPORT_MODE": legacy_mode,
        }
    )
    assert cfg.loader_name == expected


def test_loader_defaults_to_web_scrape_api() -> None:
    cfg = resolve_ingestion_config_from_mapping({"URLS": ["https://example.com"]})
    assert cfg.loader_name == "web_scrape_api"


def test_ingest_loader_auto_resolves_to_web_scrape_api() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "URLS": ["https://example.com"],
            "INGEST_LOADER": "auto",
        }
    )
    assert cfg.loader_name == "web_scrape_api"


def test_source_auto_deterministic_priority_urls_over_others() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "URLS": ["https://example.com/1"],
            "SITEMAP_URL": "https://example.com/sitemap.xml",
            "SHEETS_URL": "https://docs.google.com/spreadsheets/d/123",
            "SHEETS_NAME": "Sheet1",
            "SHEETS_SERVICE_ACCOUNT": "sa.json",
            "INGEST_LOCAL_ITEMS": [{"id": "x", "url": "https://example.com/x"}],
        }
    )
    assert cfg.source_name == "urls"
    assert any(w.code == "INGEST_CFG_MULTIPLE_LEGACY_SOURCES" for w in cfg.warnings)


def test_local_debug_alias_is_supported() -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "debug-cloud",
            "INGEST_LOADER": "passthrough",
            "INGEST_LOCAL_ITEMS": [
                {"id": "a", "url": "https://example.com", "html": "<html></html>"}
            ],
        }
    )
    assert cfg.source_name == "local"


def test_incomplete_sheets_fails_fast() -> None:
    with pytest.raises(SourceConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_SOURCE": "sheets",
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
                "URLS": ["https://example.com"],
                "INGEST_LOADER": "proxy",
                "WEB_PAGE_IMPORT_RENDER_JS": True,
            }
        )
    assert exc.value.code == "INGEST_CFG_INVALID_OPTION_COMBINATION"

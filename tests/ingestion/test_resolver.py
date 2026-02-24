from __future__ import annotations

import pytest

from wordlift_sdk.ingestion.errors import IngestionConfigError, SourceConfigError
from wordlift_sdk.ingestion.resolver import resolve_ingestion_config_from_mapping


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

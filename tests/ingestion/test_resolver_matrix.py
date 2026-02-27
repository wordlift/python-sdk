from __future__ import annotations

import pytest

from wordlift_sdk.ingestion.errors import IngestionConfigError, SourceConfigError
from wordlift_sdk.ingestion.resolver import resolve_ingestion_config_from_mapping

SOURCES = ("urls", "sitemap", "sheets")
LOADERS = (
    "simple",
    "proxy",
    "playwright",
    "premium_scraper",
    "web_scrape_api",
    "passthrough",
)


def _source_payload(source: str) -> dict[str, object]:
    if source == "urls":
        return {"URLS": ["https://example.com/a", "https://example.com/b"]}
    if source == "sitemap":
        return {
            "SITEMAP_URL": "https://example.com/sitemap.xml",
            "URL_REGEX": r"^https://example.com/articles/",
        }
    if source == "sheets":
        return {
            "SHEETS_URL": "https://docs.google.com/spreadsheets/d/123",
            "SHEETS_NAME": "Sheet1",
            "SHEETS_SERVICE_ACCOUNT": "/tmp/sa.json",
        }
    raise AssertionError(f"unsupported source {source}")


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("loader", LOADERS)
def test_explicit_source_loader_matrix_resolves(source: str, loader: str) -> None:
    cfg = resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": source,
            "INGEST_LOADER": loader,
            **_source_payload(source),
        }
    )

    assert cfg.source_name == source
    assert cfg.loader_name == loader
    assert cfg.warnings == ()


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        ("urls", "INGEST_CFG_MISSING_SOURCE"),
        ("sitemap", "INGEST_CFG_MISSING_SOURCE"),
        ("sheets", "INGEST_SRC_SHEETS_CONFIG_INVALID"),
    ],
)
def test_matrix_source_missing_required_fields_fail(
    source: str, expected_code: str
) -> None:
    payload = {
        "INGEST_SOURCE": source,
        "INGEST_LOADER": "web_scrape_api",
    }
    if source == "urls":
        payload["URLS"] = None
    elif source == "sitemap":
        payload["SITEMAP_URL"] = None
    elif source == "sheets":
        payload["SHEETS_URL"] = "https://docs.google.com/spreadsheets/d/123"
        payload["SHEETS_NAME"] = "Sheet1"
    exc_type = SourceConfigError if source == "sheets" else IngestionConfigError
    with pytest.raises(exc_type) as exc:
        resolve_ingestion_config_from_mapping(payload)
    assert exc.value.code == expected_code


def test_matrix_rejects_unsupported_source() -> None:
    with pytest.raises(IngestionConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_SOURCE": "xml_feed",
                "INGEST_LOADER": "web_scrape_api",
            }
        )
    assert exc.value.code == "INGEST_CFG_UNSUPPORTED_SOURCE"


def test_matrix_rejects_unsupported_loader() -> None:
    with pytest.raises(IngestionConfigError) as exc:
        resolve_ingestion_config_from_mapping(
            {
                "INGEST_SOURCE": "urls",
                "INGEST_LOADER": "legacy_default",
                "URLS": ["https://example.com"],
            }
        )
    assert exc.value.code == "INGEST_CFG_UNSUPPORTED_LOADER"

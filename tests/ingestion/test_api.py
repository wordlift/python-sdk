from __future__ import annotations

from wordlift_sdk.ingestion import resolve_ingestion_source_items, run_ingestion


def test_run_ingestion_with_mapping_and_passthrough() -> None:
    result = run_ingestion(
        {
            "INGEST_SOURCE": "local",
            "INGEST_LOADER": "web_scrape_api",
            "INGEST_LOCAL_ITEMS": [
                {"id": "1", "url": "https://example.com", "html": "<html>ok</html>"}
            ],
        }
    )
    assert len(result.pages) == 1
    assert result.pages[0].fetch_meta["backend"] == "passthrough"


def test_resolve_ingestion_source_items_applies_url_regex() -> None:
    result = resolve_ingestion_source_items(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com/a", "https://example.com/b"],
            "URL_REGEX": r"/a$",
        }
    )
    assert [item.url for item in result.items] == ["https://example.com/a"]
    summary = [
        event for event in result.events if event["event"] == "ingest.source_summary"
    ]
    assert len(summary) == 1
    assert summary[0]["meta"]["skipped_by_url_regex"] == 1

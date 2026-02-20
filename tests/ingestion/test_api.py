from __future__ import annotations

from wordlift_sdk.ingestion import run_ingestion


def test_run_ingestion_with_mapping_and_passthrough() -> None:
    result = run_ingestion(
        {
            "INGEST_SOURCE": "local",
            "INGEST_LOADER": "auto",
            "INGEST_LOCAL_ITEMS": [
                {"id": "1", "url": "https://example.com", "html": "<html>ok</html>"}
            ],
        }
    )
    assert len(result.pages) == 1
    assert result.pages[0].fetch_meta["backend"] == "passthrough"

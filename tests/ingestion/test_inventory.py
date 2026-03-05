from __future__ import annotations

import json

from wordlift_sdk.ingestion.api import SourceResolutionResult
from wordlift_sdk.ingestion.inventory import (
    create_structured_data_inventory_from_ingestion,
)
from wordlift_sdk.ingestion.models import LoadedPage, SourceItem
from wordlift_sdk.ingestion.orchestrator import IngestionResult
from wordlift_sdk.ingestion.resolver import ResolvedIngestionConfig


def _resolved_config() -> ResolvedIngestionConfig:
    return ResolvedIngestionConfig(
        source_name="urls",
        loader_name="simple",
        passthrough_when_html=True,
        timeout_ms=30000,
        retry_attempts=5,
        retry_backoff_ms=2000,
        source_config={},
        loader_config={},
        url_regex=None,
        warnings=tuple(),
    )


def test_create_structured_data_inventory_from_ingestion_builds_rows(
    monkeypatch,
) -> None:
    source_items = [
        SourceItem(id="u:1", url="https://example.com/a"),
        SourceItem(id="u:2", url="https://example.com/b"),
    ]
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=source_items,
            events=[],
            resolved=_resolved_config(),
        ),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.run_ingestion",
        lambda _cfg: IngestionResult(
            pages=[
                LoadedPage(
                    item_id="u:2",
                    url="https://example.com/b",
                    final_url=None,
                    status_code=200,
                    html=(
                        "<script type='application/ld+json'>"
                        '{"@type":"FAQPage","@id":"https://dataset.example/page#faq"}'
                        "</script>"
                    ),
                    fetch_meta={},
                )
            ],
            events=[],
        ),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a", "https://example.com/b"],
        },
        api_key="key",
    )

    assert list(df["url"]) == ["https://example.com/a", "https://example.com/b"]
    assert list(df["faq_markup"]) == ["no", "yes"]
    assert list(df["faq_markup_from_graph"]) == ["no", "yes"]
    assert list(df["types"]) == ["", "FAQPage"]
    assert json.loads(df.iloc[0]["structured_data"]) == {
        "@context": "https://schema.org",
        "@graph": [],
    }


def test_create_structured_data_inventory_from_ingestion_writes_csv(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=[SourceItem(id="u:1", url="https://example.com/a")],
            events=[],
            resolved=_resolved_config(),
        ),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.run_ingestion",
        lambda _cfg: IngestionResult(
            pages=[
                LoadedPage(
                    item_id="u:1",
                    url="https://example.com/a",
                    final_url="https://example.com/a?final=1",
                    status_code=200,
                    html="<html/>",
                    fetch_meta={},
                )
            ],
            events=[],
        ),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    output = tmp_path / "inventory.csv"
    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a"],
        },
        api_key="key",
        output_csv=output,
    )
    assert output.exists()
    assert df.iloc[0]["url"] == "https://example.com/a?final=1"

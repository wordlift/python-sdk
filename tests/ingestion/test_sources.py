from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from wordlift_sdk.ingestion.resolver import ResolvedIngestionConfig
from wordlift_sdk.ingestion.sources import (
    GoogleSheetsSourceAdapter,
    LocalSourceAdapter,
    SitemapSourceAdapter,
    UrlListSourceAdapter,
)


def _config(**kwargs) -> ResolvedIngestionConfig:
    defaults = {
        "source_name": "urls",
        "loader_name": "simple",
        "passthrough_when_html": True,
        "timeout_ms": 30000,
        "retry_attempts": 1,
        "retry_backoff_ms": 1,
        "source_config": {},
        "loader_config": {},
        "warnings": tuple(),
    }
    defaults.update(kwargs)
    return ResolvedIngestionConfig(**defaults)


def test_url_list_source_adapter() -> None:
    adapter = UrlListSourceAdapter()
    items = list(
        adapter.iter_items(_config(source_config={"urls": ["https://a", "https://b"]}))
    )
    assert [i.url for i in items] == ["https://a", "https://b"]


def test_sitemap_source_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = SitemapSourceAdapter()

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.adv.sitemaps.sitemap_to_df",
        lambda sitemap_url: pd.DataFrame(
            {
                "loc": ["https://example.com/1", "https://example.com/skip"],
                "lastmod": ["2026-01-01", None],
            }
        ),
    )

    cfg = _config(
        source_config={
            "sitemap_url": "https://example.com/sitemap.xml",
            "sitemap_url_pattern": r"^https://example.com/1$",
        }
    )

    items = list(adapter.iter_items(cfg))
    assert len(items) == 1
    assert items[0].url == "https://example.com/1"
    assert "date_modified" in items[0].metadata


def test_google_sheets_source_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = GoogleSheetsSourceAdapter()

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.gspread.service_account",
        lambda filename: object(),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.create_dataframe_from_google_sheets",
        lambda creds, url, sheet: pd.DataFrame(
            {
                "url": ["https://example.com/a", "https://example.com/b"],
                "kind": ["a", "b"],
            }
        ),
    )

    cfg = _config(
        source_config={
            "sheets_url": "https://docs.google.com/spreadsheets/d/123",
            "sheets_name": "Sheet1",
            "sheets_service_account": "sa.json",
        }
    )
    items = list(adapter.iter_items(cfg))
    assert len(items) == 2
    assert items[0].metadata["kind"] == "a"


def test_local_source_adapter_embedded_html(tmp_path: Path) -> None:
    adapter = LocalSourceAdapter()

    items = list(
        adapter.iter_items(
            _config(
                source_config={
                    "items": [
                        {
                            "id": "local-1",
                            "url": "https://example.com/local",
                            "html": "<html>local</html>",
                            "metadata": {"source": "debug"},
                        }
                    ],
                    "file": None,
                }
            )
        )
    )

    assert len(items) == 1
    assert items[0].html == "<html>local</html>"
    assert items[0].metadata["source"] == "debug"

    file_path = tmp_path / "local.json"
    file_path.write_text(
        json.dumps(
            [
                {
                    "id": "file-1",
                    "url": "https://example.com/file",
                    "html": "<html>file</html>",
                }
            ]
        ),
        encoding="utf-8",
    )

    file_items = list(
        adapter.iter_items(
            _config(source_config={"items": None, "file": str(file_path)})
        )
    )
    assert len(file_items) == 1
    assert file_items[0].id == "file-1"

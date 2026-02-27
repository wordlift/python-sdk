from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from wordlift_sdk.ingestion.errors import SourceConfigError, SourceRuntimeError
from wordlift_sdk.ingestion.resolver import ResolvedIngestionConfig
from wordlift_sdk.render.render_options import DEFAULT_USER_AGENT
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

    items_from_str = list(
        adapter.iter_items(_config(source_config={"urls": "https://a,\nhttps://b"}))
    )
    assert [i.url for i in items_from_str] == ["https://a", "https://b"]

    assert list(adapter.iter_items(_config(source_config={"urls": None}))) == []
    with pytest.raises(SourceConfigError):
        list(adapter.iter_items(_config(source_config={"urls": 123})))


def test_sitemap_source_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = SitemapSourceAdapter()
    calls: list[dict[str, object]] = []

    def _mock_sitemap_to_df(*, sitemap_url: str, request_headers: dict[str, str]):
        calls.append({"sitemap_url": sitemap_url, "request_headers": request_headers})
        return pd.DataFrame(
            {
                "loc": ["https://example.com/1", "https://example.com/skip"],
                "lastmod": ["2026-01-01", None],
            }
        )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.adv.sitemaps.sitemap_to_df",
        _mock_sitemap_to_df,
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
    assert calls == [
        {
            "sitemap_url": "https://example.com/sitemap.xml",
            "request_headers": {"User-Agent": DEFAULT_USER_AGENT},
        }
    ]


def test_sitemap_source_adapter_handles_missing_lastmod_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SitemapSourceAdapter()
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.adv.sitemaps.sitemap_to_df",
        lambda *, sitemap_url, request_headers: pd.DataFrame(
            {"loc": ["https://example.com/1", ""]}
        ),
    )
    items = list(
        adapter.iter_items(
            _config(source_config={"sitemap_url": "https://example.com/sitemap.xml"})
        )
    )
    assert len(items) == 1
    assert items[0].metadata == {}

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.adv.sitemaps.sitemap_to_df",
        lambda *, sitemap_url, request_headers: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )
    with pytest.raises(SourceRuntimeError):
        list(
            adapter.iter_items(
                _config(
                    source_config={"sitemap_url": "https://example.com/sitemap.xml"}
                )
            )
        )


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


def test_google_sheets_source_adapter_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = GoogleSheetsSourceAdapter()
    cfg = _config(
        source_config={
            "sheets_url": "https://docs.google.com/spreadsheets/d/123",
            "sheets_name": "Sheet1",
            "sheets_service_account": "sa.json",
        }
    )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.gspread.service_account",
        lambda filename: (_ for _ in ()).throw(RuntimeError("bad sa")),
    )
    with pytest.raises(SourceConfigError):
        list(adapter.iter_items(cfg))

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.gspread.service_account",
        lambda filename: object(),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.create_dataframe_from_google_sheets",
        lambda creds, url, sheet: (_ for _ in ()).throw(RuntimeError("read fail")),
    )
    with pytest.raises(SourceRuntimeError):
        list(adapter.iter_items(cfg))

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.sources.create_dataframe_from_google_sheets",
        lambda creds, url, sheet: pd.DataFrame({"kind": ["a"]}),
    )
    with pytest.raises(SourceConfigError):
        list(adapter.iter_items(cfg))


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


def test_local_source_adapter_error_and_file_format_paths(tmp_path: Path) -> None:
    adapter = LocalSourceAdapter()

    with pytest.raises(SourceConfigError):
        list(adapter.iter_items(_config(source_config={"items": None, "file": None})))

    with pytest.raises(SourceConfigError):
        list(
            adapter.iter_items(
                _config(source_config={"items": "not-a-list", "file": None})
            )
        )

    with pytest.raises(SourceConfigError):
        list(
            adapter.iter_items(_config(source_config={"items": ["bad"], "file": None}))
        )

    with pytest.raises(SourceConfigError):
        list(
            adapter.iter_items(
                _config(
                    source_config={
                        "items": [
                            {"id": "1", "url": "https://example.com", "metadata": "x"}
                        ],
                        "file": None,
                    }
                )
            )
        )

    missing_file = tmp_path / "missing.json"
    with pytest.raises(SourceConfigError):
        list(
            adapter.iter_items(
                _config(source_config={"items": None, "file": str(missing_file)})
            )
        )

    jsonl_path = tmp_path / "local.jsonl"
    jsonl_path.write_text(
        '\n{"id":"j1","url":"https://example.com/j1"}\n\n{"id":"j2","url":"https://example.com/j2"}\n',
        encoding="utf-8",
    )
    items = list(
        adapter.iter_items(
            _config(source_config={"items": None, "file": str(jsonl_path)})
        )
    )
    assert [item.id for item in items] == ["j1", "j2"]

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text(json.dumps({"id": "x"}), encoding="utf-8")
    with pytest.raises(SourceConfigError):
        list(
            adapter.iter_items(
                _config(source_config={"items": None, "file": str(invalid_json)})
            )
        )

    txt_path = tmp_path / "local.txt"
    txt_path.write_text("x", encoding="utf-8")
    with pytest.raises(SourceConfigError):
        list(
            adapter.iter_items(
                _config(source_config={"items": None, "file": str(txt_path)})
            )
        )

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from wordlift_sdk.ingestion.type_classification import (
    create_type_classification_csv_from_ingestion,
)


def test_create_type_classification_csv_from_ingestion(
    tmp_path: Path, monkeypatch
) -> None:
    output_csv = tmp_path / "types.csv"

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.run_ingestion",
        lambda cfg: SimpleNamespace(
            pages=[
                SimpleNamespace(
                    url="https://example.com/a",
                    final_url=None,
                    html="<html>a</html>",
                ),
                SimpleNamespace(
                    url="https://example.com/b",
                    final_url="https://example.com/b-final",
                    html="<html>b</html>",
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification._extract_markdown_body",
        lambda html, max_markdown_chars: f"md:{html}",
    )

    class _Runner:
        def __init__(self, cli, timeout_sec):
            assert cli == "codex"
            assert timeout_sec == 11.0

        def run_json(self, prompt: str):
            assert "MARKDOWN_BODY" in prompt
            return {
                "main_type": "Article",
                "additional_types": ["NewsArticle", "BlogPosting"],
                "explanation": "content is article-like",
            }

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.LocalAgentCliRunner", _Runner
    )

    result = create_type_classification_csv_from_ingestion(
        source_bundle={
            "ingest-source": "urls",
            "ingest-loader": "web_scrape_api",
            "urls": ["https://example.com/a", "https://example.com/b"],
            "url-regex": r"example\\.com",
        },
        output_csv=output_csv,
        agent_cli="codex",
        agent_timeout_sec=11.0,
    )

    assert list(result.columns) == [
        "url",
        "main_type",
        "additional_types",
        "explanation",
    ]
    assert result.iloc[0]["url"] == "https://example.com/a"
    assert result.iloc[1]["url"] == "https://example.com/b-final"
    assert output_csv.exists()
    written = pd.read_csv(output_csv)
    assert written.equals(result)


def test_create_type_classification_requires_extraction(
    tmp_path: Path, monkeypatch
) -> None:
    output_csv = tmp_path / "types.csv"
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.run_ingestion",
        lambda cfg: SimpleNamespace(
            pages=[
                SimpleNamespace(
                    url="https://example.com/a",
                    final_url=None,
                    html="<html>a</html>",
                ),
            ]
        ),
    )

    class _Runner:
        def __init__(self, cli, timeout_sec):
            del cli, timeout_sec

        def run_json(self, prompt: str):
            del prompt
            return {
                "main_type": "Article",
                "additional_types": [],
                "explanation": "ok",
            }

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.LocalAgentCliRunner", _Runner
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification._extract_markdown_body",
        lambda html, max_markdown_chars: (_ for _ in ()).throw(
            RuntimeError("Failed to extract")
        ),
    )

    import pytest

    with pytest.raises(RuntimeError, match="Failed to extract"):
        create_type_classification_csv_from_ingestion(
            source_bundle={
                "INGEST_SOURCE": "urls",
                "INGEST_LOADER": "web_scrape_api",
                "URLS": ["https://example.com/a"],
            },
            output_csv=output_csv,
        )

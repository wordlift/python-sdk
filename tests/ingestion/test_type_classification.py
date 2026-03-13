from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from wordlift_sdk.agent_cli import AgentCliError
from wordlift_sdk.ingestion.type_classification import (
    _extract_markdown_body,
    _classification_prompt,
    _google_search_gallery_type_groups,
    _normalize_source_bundle,
    _resume_state_path,
    _row_from_payload,
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


def test_create_type_classification_skips_failed_pages_after_retries(
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
    sleeps: list[float] = []
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.time.sleep", sleeps.append
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

    result = create_type_classification_csv_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com/a"],
        },
        output_csv=output_csv,
    )

    assert sleeps == [3.0, 3.0]
    assert result.iloc[0]["url"] == "https://example.com/a"
    assert result.iloc[0]["main_type"] == ""
    assert result.iloc[0]["additional_types"] == "[]"
    assert "Classification failed after 3 attempts" in result.iloc[0]["explanation"]
    assert "RuntimeError: Failed to extract" in result.iloc[0]["explanation"]


def test_create_type_classification_emits_progress_on_success(
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

    events: list[dict[str, object]] = []
    create_type_classification_csv_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com/a", "https://example.com/b"],
        },
        output_csv=output_csv,
        on_progress=events.append,
    )

    assert [event["event"] for event in events] == [
        "type_classification.progress.started",
        "type_classification.progress.updated",
        "type_classification.progress.updated",
        "type_classification.progress.completed",
    ]
    assert events[0]["meta"] == {"total": 2}
    assert events[1]["meta"] == {
        "total": 2,
        "completed": 1,
        "remaining": 1,
        "url": "https://example.com/a",
        "status": "ok",
    }
    assert events[2]["meta"] == {
        "total": 2,
        "completed": 2,
        "remaining": 0,
        "url": "https://example.com/b-final",
        "status": "ok",
    }
    assert events[3]["meta"] == {"total": 2, "completed": 2}


def test_create_type_classification_emits_progress_for_skipped_page(
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
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification._extract_markdown_body",
        lambda html, max_markdown_chars: (_ for _ in ()).throw(
            RuntimeError("Failed to extract")
        ),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.time.sleep", lambda seconds: None
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

    events: list[dict[str, object]] = []
    result = create_type_classification_csv_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com/a"],
        },
        output_csv=output_csv,
        on_progress=events.append,
    )

    assert [event["event"] for event in events] == [
        "type_classification.progress.started",
        "type_classification.progress.updated",
        "type_classification.progress.completed",
    ]
    assert events[0]["meta"] == {"total": 1}
    assert events[1]["meta"]["status"] == "skipped"
    assert events[1]["meta"]["error_type"] == "RuntimeError"
    assert events[1]["meta"]["error_message"] == "Failed to extract"
    assert events[2]["meta"] == {"total": 1, "completed": 1}
    assert "Classification failed after 3 attempts" in result.iloc[0]["explanation"]


def test_create_type_classification_retries_agent_cli_errors_then_recovers(
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
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification._extract_markdown_body",
        lambda html, max_markdown_chars: "md",
    )
    sleeps: list[float] = []
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.time.sleep", sleeps.append
    )

    class _Runner:
        calls = 0

        def __init__(self, cli, timeout_sec):
            del cli, timeout_sec

        def run_json(self, prompt: str):
            del prompt
            type(self).calls += 1
            if type(self).calls < 3:
                raise AgentCliError("codex failed")
            return {
                "main_type": "Article",
                "additional_types": [],
                "explanation": "ok",
            }

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.LocalAgentCliRunner", _Runner
    )

    result = create_type_classification_csv_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "web_scrape_api",
            "URLS": ["https://example.com/a"],
        },
        output_csv=output_csv,
    )

    assert _Runner.calls == 3
    assert sleeps == [3.0, 3.0]
    assert result.iloc[0]["main_type"] == "Article"


def test_create_type_classification_resumes_by_default_across_cli_choice(
    tmp_path: Path, monkeypatch
) -> None:
    output_csv = tmp_path / "types.csv"
    source_bundle = {
        "INGEST_SOURCE": "urls",
        "INGEST_LOADER": "web_scrape_api",
        "URLS": ["https://example.com/a"],
    }
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
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification._extract_markdown_body",
        lambda html, max_markdown_chars: "md",
    )

    class _Runner:
        calls = 0

        def __init__(self, cli, timeout_sec):
            del cli, timeout_sec

        def run_json(self, prompt: str):
            del prompt
            type(self).calls += 1
            return {
                "main_type": "Article",
                "additional_types": [],
                "explanation": "ok",
            }

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.LocalAgentCliRunner", _Runner
    )

    first = create_type_classification_csv_from_ingestion(
        source_bundle=source_bundle,
        output_csv=output_csv,
        agent_cli="codex",
    )
    second = create_type_classification_csv_from_ingestion(
        source_bundle=source_bundle,
        output_csv=output_csv,
        agent_cli="claude",
    )

    assert _Runner.calls == 1
    assert first.equals(second)


def test_resume_state_path_excludes_agent_cli_from_call_state(tmp_path: Path) -> None:
    source_bundle = {
        "INGEST_SOURCE": "urls",
        "INGEST_LOADER": "web_scrape_api",
        "URLS": ["https://example.com/a"],
    }

    first = _resume_state_path(
        output_csv=tmp_path / "types.csv",
        source_bundle=source_bundle,
        agent_timeout_sec=120.0,
        max_markdown_chars=24000,
    )
    second = _resume_state_path(
        output_csv=tmp_path / "types.csv",
        source_bundle=source_bundle,
        agent_timeout_sec=120.0,
        max_markdown_chars=24000,
    )
    third = _resume_state_path(
        output_csv=tmp_path / "types.csv",
        source_bundle=source_bundle,
        agent_timeout_sec=120.0,
        max_markdown_chars=24000,
    )

    assert first == second
    assert first == third


def test_create_type_classification_no_resume_reprocesses_pages(
    tmp_path: Path, monkeypatch
) -> None:
    output_csv = tmp_path / "types.csv"
    source_bundle = {
        "INGEST_SOURCE": "urls",
        "INGEST_LOADER": "web_scrape_api",
        "URLS": ["https://example.com/a"],
    }
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
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification._extract_markdown_body",
        lambda html, max_markdown_chars: "md",
    )

    class _Runner:
        calls = 0

        def __init__(self, cli, timeout_sec):
            del cli, timeout_sec

        def run_json(self, prompt: str):
            del prompt
            type(self).calls += 1
            return {
                "main_type": "Article",
                "additional_types": [],
                "explanation": f"ok-{type(self).calls}",
            }

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.type_classification.LocalAgentCliRunner", _Runner
    )

    first = create_type_classification_csv_from_ingestion(
        source_bundle=source_bundle,
        output_csv=output_csv,
    )
    second = create_type_classification_csv_from_ingestion(
        source_bundle=source_bundle,
        output_csv=output_csv,
        no_resume=True,
    )

    assert _Runner.calls == 2
    assert first.iloc[0]["explanation"] == "ok-1"
    assert second.iloc[0]["explanation"] == "ok-2"


def test_normalize_source_bundle_normalizes_keys() -> None:
    assert _normalize_source_bundle({" ingest-source ": "urls", "url-regex": ".*"}) == {
        "INGEST_SOURCE": "urls",
        "URL_REGEX": ".*",
    }


def test_extract_markdown_body_truncates(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "trafilatura",
        SimpleNamespace(extract=lambda *args, **kwargs: "  abcdef  "),
    )
    assert _extract_markdown_body("<html/>", max_markdown_chars=3) == "abc"


def test_extract_markdown_body_raises_when_empty(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "trafilatura",
        SimpleNamespace(extract=lambda *args, **kwargs: None),
    )
    with pytest.raises(RuntimeError, match="Failed to extract markdown body"):
        _extract_markdown_body("<html/>", max_markdown_chars=10)


def test_google_search_gallery_type_groups_split_primary_and_supporting() -> None:
    primary_types, supporting_types = _google_search_gallery_type_groups()

    assert "Article" in primary_types
    assert "Product" in primary_types
    assert "FAQPage" in primary_types
    assert "Offer" not in primary_types
    assert "Offer" in supporting_types
    assert "Rating" in supporting_types


def test_classification_prompt_constrains_output_to_project_vocabularies() -> None:
    prompt = _classification_prompt(
        url="https://example.com/article",
        markdown="# Title\n\nBody text",
    )

    assert "Prefer a Google Search Gallery primary type" in prompt
    assert "Do not invent types outside these lists" in prompt
    assert "Google Search Gallery primary types:" in prompt
    assert "Google Search Gallery supporting or nested types" in prompt
    assert "Broader schema.org fallback types:" in prompt
    assert "Article" in prompt
    assert "Product" in prompt
    assert "FAQPage" in prompt
    assert "Offer" in prompt
    assert "WebPage" in prompt
    assert "CollectionPage" in prompt


def test_row_from_payload_supports_string_and_default_additional_types() -> None:
    row = _row_from_payload(
        url="https://example.com/a",
        payload={
            "main_type": "Article",
            "additional_types": "NewsArticle, BlogPosting",
            "explanation": "ok",
        },
    )
    assert row["additional_types"] == '["NewsArticle", "BlogPosting"]'

    row = _row_from_payload(
        url="https://example.com/b",
        payload={"main_type": "Article", "additional_types": 1, "explanation": "ok"},
    )
    assert row["additional_types"] == "[]"


def test_row_from_payload_validates_required_keys() -> None:
    with pytest.raises(AgentCliError, match="missing required key 'main_type'"):
        _row_from_payload(
            url="https://example.com/a",
            payload={"additional_types": [], "explanation": "ok"},
        )
    with pytest.raises(AgentCliError, match="missing required key 'explanation'"):
        _row_from_payload(
            url="https://example.com/a",
            payload={"main_type": "Article", "additional_types": []},
        )

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from wordlift_sdk.agent_cli import AgentCliError, LocalAgentCliRunner

from .api import run_ingestion


def create_type_classification_csv_from_ingestion(
    *,
    source_bundle: Mapping[str, Any],
    output_csv: str | Path,
    agent_cli: str | None = None,
    agent_timeout_sec: float = 120.0,
    max_markdown_chars: int = 24000,
) -> pd.DataFrame:
    """Classify ingested URLs and write `url,main_type,additional_types,explanation`."""

    ingest_config = _normalize_source_bundle(source_bundle)
    ingestion_result = run_ingestion(ingest_config)
    runner = LocalAgentCliRunner(cli=agent_cli, timeout_sec=agent_timeout_sec)

    rows: list[dict[str, str]] = []
    for page in ingestion_result.pages:
        url = page.final_url or page.url
        markdown = _extract_markdown_body(
            page.html, max_markdown_chars=max_markdown_chars
        )
        payload = runner.run_json(_classification_prompt(url=url, markdown=markdown))
        rows.append(_row_from_payload(url=url, payload=payload))

    result = pd.DataFrame(
        rows,
        columns=["url", "main_type", "additional_types", "explanation"],
    )
    result.to_csv(output_csv, index=False)
    return result


def _normalize_source_bundle(source_bundle: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in source_bundle.items():
        normalized = str(key).strip().upper().replace("-", "_")
        out[normalized] = value
    return out


def _extract_markdown_body(html: str, *, max_markdown_chars: int) -> str:
    import trafilatura

    markdown = trafilatura.extract(
        html,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
    )
    if not markdown:
        raise RuntimeError("Failed to extract markdown body with trafilatura.")
    normalized = markdown.strip()
    if len(normalized) > max_markdown_chars:
        return normalized[:max_markdown_chars]
    return normalized


def _classification_prompt(*, url: str, markdown: str) -> str:
    return (
        "You are an expert in schema.org typing for web pages.\n"
        "Given a URL and its meaningful markdown body, infer the best entity types.\n"
        "Return JSON only with exactly these keys:\n"
        "- main_type: string\n"
        "- additional_types: array of strings\n"
        "- explanation: string\n"
        "Use schema.org type names without full URLs.\n"
        "Do not include markdown, code fences, or extra keys.\n\n"
        f"URL: {url}\n"
        "MARKDOWN_BODY:\n"
        f"{markdown}\n"
    )


def _row_from_payload(*, url: str, payload: dict[str, object]) -> dict[str, str]:
    main_type = str(payload.get("main_type") or "").strip()
    additional_raw = payload.get("additional_types")
    if isinstance(additional_raw, list):
        additional_values = [
            str(item).strip() for item in additional_raw if str(item).strip()
        ]
    elif isinstance(additional_raw, str):
        additional_values = [
            part.strip() for part in additional_raw.split(",") if part.strip()
        ]
    else:
        additional_values = []
    explanation = str(payload.get("explanation") or "").strip()

    if not main_type:
        raise AgentCliError(
            "Agent CLI JSON output is missing required key 'main_type'."
        )
    if not explanation:
        raise AgentCliError(
            "Agent CLI JSON output is missing required key 'explanation'."
        )

    return {
        "url": url,
        "main_type": main_type,
        "additional_types": json.dumps(additional_values, ensure_ascii=True),
        "explanation": explanation,
    }


__all__ = ["create_type_classification_csv_from_ingestion"]

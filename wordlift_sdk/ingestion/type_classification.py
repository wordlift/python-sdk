from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping

import pandas as pd

from wordlift_sdk.agent_cli import AgentCliError, LocalAgentCliRunner
from wordlift_sdk.utils.auto_concurrency import AutoConcurrencyController

from .api import run_ingestion


_GOOGLE_SHACL_TARGET_CLASS_RE = re.compile(
    r"sh:targetClass\s+schema:([A-Za-z][A-Za-z0-9]+)"
)
_GOOGLE_SUPPORTING_TYPES = frozenset(
    {
        "BroadcastEvent",
        "Certification",
        "Claim",
        "Clip",
        "Comment",
        "Conditions",
        "DataCatalog",
        "DataDownload",
        "DataFeed",
        "DefinedRegion",
        "Edition",
        "HowToDirection",
        "HowToSection",
        "HowToTip",
        "ImageObject",
        "InteractionCounter",
        "ItemList",
        "Library",
        "LibrarySystem",
        "MemberProgram",
        "MemberProgramTier",
        "MerchantReturnPolicy",
        "MonetaryAmount",
        "Offer",
        "OfferShippingDetails",
        "OpeningHoursSpecification",
        "PeopleAudience",
        "QuantitativeValue",
        "Rating",
        "SeekToAction",
        "ServicePeriod",
        "ShippingConditions",
        "ShippingDeliveryTime",
        "ShippingRateSettings",
        "ShippingService",
        "SizeSpecification",
        "UnitPriceSpecification",
        "Work",
        "speakable",
    }
)
_SCHEMA_FALLBACK_TYPES = (
    "WebPage",
    "AboutPage",
    "CollectionPage",
    "ItemPage",
    "SearchResultsPage",
    "ProfilePage",
    "Article",
    "BlogPosting",
    "NewsArticle",
    "TechArticle",
    "Report",
    "AnalysisNewsArticle",
    "OpinionNewsArticle",
    "ReviewNewsArticle",
    "LiveBlogPosting",
    "Product",
    "ProductGroup",
    "Service",
    "SoftwareApplication",
    "WebSite",
    "Organization",
    "LocalBusiness",
    "Person",
    "CreativeWork",
    "Course",
    "Event",
    "JobPosting",
    "Recipe",
    "VideoObject",
    "FAQPage",
    "QAPage",
    "DiscussionForumPosting",
    "Dataset",
    "Book",
    "Movie",
    "Review",
)
_CLASSIFICATION_MAX_ATTEMPTS = 3
_CLASSIFICATION_RETRY_WAIT_SEC = 3.0


def create_type_classification_csv_from_ingestion(
    *,
    source_bundle: Mapping[str, Any],
    output_csv: str | Path,
    agent_cli: str | None = None,
    agent_timeout_sec: float = 120.0,
    max_markdown_chars: int = 24000,
    concurrency: str = "auto",
    auto_min_concurrency: int = 2,
    auto_max_concurrency: int = 12,
    auto_initial_concurrency: int = 4,
    no_resume: bool = False,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> pd.DataFrame:
    """Classify ingested URLs and write `url,main_type,additional_types,explanation`."""

    ingest_config = _normalize_source_bundle(source_bundle)
    ingestion_result = run_ingestion(ingest_config)
    resolved_output_csv = Path(output_csv)
    state_path = _resume_state_path(
        output_csv=resolved_output_csv,
        source_bundle=ingest_config,
        agent_timeout_sec=agent_timeout_sec,
        max_markdown_chars=max_markdown_chars,
    )
    resume_rows = {} if no_resume else _load_resume_rows(state_path)
    concurrency_controller = AutoConcurrencyController.from_value(
        concurrency,
        min_auto_workers=auto_min_concurrency,
        max_auto_workers=auto_max_concurrency,
        initial_auto_workers=auto_initial_concurrency,
    )

    total = len(ingestion_result.pages)
    rows_by_index: dict[int, dict[str, str]] = {}
    pending: list[tuple[int, Any, str]] = []
    if on_progress is not None:
        on_progress(
            {
                "event": "type_classification.progress.started",
                "timestamp": _utc_now_iso(),
                "meta": {"total": total},
            }
        )

    for index, page in enumerate(ingestion_result.pages, start=1):
        url = page.final_url or page.url
        resumed_row = resume_rows.get(index)
        if resumed_row is not None and resumed_row.get("url") == url:
            row = _coerce_resume_row(resumed_row)
            rows_by_index[index] = row
            if on_progress is not None:
                on_progress(
                    {
                        "event": "type_classification.progress.updated",
                        "timestamp": _utc_now_iso(),
                        "meta": {
                            "total": total,
                            "completed": index,
                            "remaining": total - index,
                            "url": url,
                            "status": "resumed",
                        },
                    }
                )
            continue
        pending.append((index, page, url))

    processed = len(rows_by_index)
    while pending:
        batch = pending[: concurrency_controller.current_workers]
        pending = pending[concurrency_controller.current_workers :]
        batch_results: list[tuple[int, str, dict[str, str], Exception | None]] = []
        with ThreadPoolExecutor(
            max_workers=concurrency_controller.current_workers
        ) as executor:
            futures = {
                executor.submit(
                    _classify_page_task,
                    page_html=page.html,
                    url=url,
                    agent_cli=agent_cli,
                    agent_timeout_sec=agent_timeout_sec,
                    max_markdown_chars=max_markdown_chars,
                ): (index, url)
                for index, page, url in batch
            }
            for future in as_completed(futures):
                index, url = futures[future]
                row, error = future.result()
                batch_results.append((index, url, row, error))

        status_codes: list[int | None] = []
        for index, url, row, error in sorted(batch_results, key=lambda item: item[0]):
            rows_by_index[index] = row
            _write_resume_row(state_path, index=index, row=row)
            processed += 1
            if error is None:
                status = "ok"
                status_codes.append(200)
            else:
                status = "skipped"
                status_codes.append(None)
            if on_progress is not None:
                meta = {
                    "total": total,
                    "completed": processed,
                    "remaining": total - processed,
                    "url": url,
                    "status": status,
                }
                if error is not None:
                    meta["error_type"] = type(error).__name__
                    meta["error_message"] = str(error)
                on_progress(
                    {
                        "event": "type_classification.progress.updated",
                        "timestamp": _utc_now_iso(),
                        "meta": meta,
                    }
                )
        concurrency_controller.update_from_status_codes(status_codes)

    rows = [rows_by_index[index] for index in range(1, total + 1)]
    result = pd.DataFrame(
        rows,
        columns=["url", "main_type", "additional_types", "explanation"],
    )
    result.to_csv(resolved_output_csv, index=False)
    if on_progress is not None:
        on_progress(
            {
                "event": "type_classification.progress.completed",
                "timestamp": _utc_now_iso(),
                "meta": {"total": total, "completed": total},
            }
        )
    return result


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_source_bundle(source_bundle: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in source_bundle.items():
        normalized = str(key).strip().upper().replace("-", "_")
        out[normalized] = value
    return out


def _resume_state_path(
    *,
    output_csv: str | Path,
    source_bundle: Mapping[str, Any],
    agent_timeout_sec: float,
    max_markdown_chars: int,
) -> Path:
    output_path = Path(output_csv)
    call_state = {
        "source_bundle": dict(source_bundle),
        "output_csv": str(output_path.resolve()),
        "agent_timeout_sec": agent_timeout_sec,
        "max_markdown_chars": max_markdown_chars,
    }
    serialized = json.dumps(call_state, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
    return output_path.parent / f".{output_path.name}.{digest}.resume.json"


def _load_resume_rows(state_path: Path) -> dict[int, dict[str, str]]:
    try:
        payload = json.loads(state_path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    items = payload.get("rows")
    if not isinstance(items, list):
        return {}
    rows: dict[int, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        row = item.get("row")
        if isinstance(index, int) and isinstance(row, dict):
            rows[index] = {
                "url": str(row.get("url") or ""),
                "main_type": str(row.get("main_type") or ""),
                "additional_types": str(row.get("additional_types") or "[]"),
                "explanation": str(row.get("explanation") or ""),
            }
    return rows


def _write_resume_row(state_path: Path, *, index: int, row: dict[str, str]) -> None:
    rows = _load_resume_rows(state_path)
    rows[index] = dict(row)
    payload = {"rows": [{"index": idx, "row": rows[idx]} for idx in sorted(rows)]}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_suffix(f"{state_path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2))
    temp_path.replace(state_path)


def _coerce_resume_row(row: Mapping[str, object]) -> dict[str, str]:
    return {
        "url": str(row.get("url") or ""),
        "main_type": str(row.get("main_type") or ""),
        "additional_types": str(row.get("additional_types") or "[]"),
        "explanation": str(row.get("explanation") or ""),
    }


def _classify_page_with_retries(
    *,
    page_html: str,
    url: str,
    runner: LocalAgentCliRunner,
    max_markdown_chars: int,
) -> dict[str, str]:
    last_exc: Exception | None = None
    for attempt in range(1, _CLASSIFICATION_MAX_ATTEMPTS + 1):
        try:
            markdown = _extract_markdown_body(
                page_html, max_markdown_chars=max_markdown_chars
            )
            payload = runner.run_json(
                _classification_prompt(url=url, markdown=markdown)
            )
            return _row_from_payload(url=url, payload=payload)
        except Exception as exc:
            last_exc = exc
            if attempt >= _CLASSIFICATION_MAX_ATTEMPTS:
                break
            time.sleep(_CLASSIFICATION_RETRY_WAIT_SEC)
    assert last_exc is not None
    raise last_exc


def _classify_page_task(
    *,
    page_html: str,
    url: str,
    agent_cli: str | None,
    agent_timeout_sec: float,
    max_markdown_chars: int,
) -> tuple[dict[str, str], Exception | None]:
    runner = LocalAgentCliRunner(cli=agent_cli, timeout_sec=agent_timeout_sec)
    try:
        row = _classify_page_with_retries(
            page_html=page_html,
            url=url,
            runner=runner,
            max_markdown_chars=max_markdown_chars,
        )
        return row, None
    except Exception as exc:
        return _error_row(url=url, exc=exc), exc


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


def _error_row(*, url: str, exc: Exception) -> dict[str, str]:
    return {
        "url": url,
        "main_type": "",
        "additional_types": "[]",
        "explanation": (
            "Classification failed after "
            f"{_CLASSIFICATION_MAX_ATTEMPTS} attempts: "
            f"{type(exc).__name__}: {exc}"
        ),
    }


@lru_cache(maxsize=1)
def _google_search_gallery_type_groups() -> tuple[tuple[str, ...], tuple[str, ...]]:
    shacls_dir = Path(__file__).resolve().parent.parent / "validation" / "shacls"
    primary_types: set[str] = set()
    supporting_types: set[str] = set()
    for path in sorted(shacls_dir.glob("google-*.ttl")):
        for type_name in _GOOGLE_SHACL_TARGET_CLASS_RE.findall(path.read_text()):
            if type_name in _GOOGLE_SUPPORTING_TYPES:
                supporting_types.add(type_name)
            else:
                primary_types.add(type_name)
    return tuple(sorted(primary_types)), tuple(sorted(supporting_types))


def _classification_prompt(*, url: str, markdown: str) -> str:
    google_primary_types, google_supporting_types = _google_search_gallery_type_groups()
    schema_fallback_types = ", ".join(_SCHEMA_FALLBACK_TYPES)
    google_primary_types_text = ", ".join(google_primary_types)
    google_supporting_types_text = ", ".join(google_supporting_types)
    return (
        "You are an expert in schema.org typing for web pages.\n"
        "Given a URL and its meaningful markdown body, infer the best entity types.\n"
        "Reduce hallucinations by choosing from the allowed type lists below.\n"
        "Prefer a Google Search Gallery primary type when the page clearly matches one.\n"
        "Only fall back to the broader schema.org types when no Google Search Gallery primary type fits.\n"
        "Use Google supporting/nested types only when they are clearly secondary, not as the page's main type.\n"
        "Do not invent types outside these lists unless the page unambiguously requires a standard schema.org subtype.\n"
        "Choose a single best `main_type` for the page/root entity.\n"
        "Use `additional_types` only for close, defensible companion types; keep the list short and avoid duplicates.\n"
        "Return JSON only with exactly these keys:\n"
        "- main_type: string\n"
        "- additional_types: array of strings\n"
        "- explanation: string\n"
        "Use schema.org type names without full URLs.\n"
        "Do not include markdown, code fences, or extra keys.\n\n"
        "Google Search Gallery primary types:\n"
        f"{google_primary_types_text}\n\n"
        "Google Search Gallery supporting or nested types (usually additional_types only):\n"
        f"{google_supporting_types_text}\n\n"
        "Broader schema.org fallback types:\n"
        f"{schema_fallback_types}\n\n"
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

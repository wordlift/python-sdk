from __future__ import annotations

from functools import lru_cache
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable, Mapping

import pandas as pd

from wordlift_sdk.agent_cli import AgentCliError, LocalAgentCliRunner

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


def create_type_classification_csv_from_ingestion(
    *,
    source_bundle: Mapping[str, Any],
    output_csv: str | Path,
    agent_cli: str | None = None,
    agent_timeout_sec: float = 120.0,
    max_markdown_chars: int = 24000,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> pd.DataFrame:
    """Classify ingested URLs and write `url,main_type,additional_types,explanation`."""

    ingest_config = _normalize_source_bundle(source_bundle)
    ingestion_result = run_ingestion(ingest_config)
    runner = LocalAgentCliRunner(cli=agent_cli, timeout_sec=agent_timeout_sec)

    rows: list[dict[str, str]] = []
    total = len(ingestion_result.pages)
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
        try:
            markdown = _extract_markdown_body(
                page.html, max_markdown_chars=max_markdown_chars
            )
            payload = runner.run_json(
                _classification_prompt(url=url, markdown=markdown)
            )
            rows.append(_row_from_payload(url=url, payload=payload))
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
                            "status": "ok",
                        },
                    }
                )
        except Exception as exc:
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
                            "status": "error",
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        },
                    }
                )
            raise

    result = pd.DataFrame(
        rows,
        columns=["url", "main_type", "additional_types", "explanation"],
    )
    result.to_csv(output_csv, index=False)
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

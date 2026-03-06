from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from wordlift_sdk.structured_data.structured_data_engine import StructuredDataEngine

from .api import resolve_ingestion_source_items
from .factory import create_orchestrator


@dataclass(frozen=True)
class StructuredDataInventoryRow:
    url: str
    faq_markup: str
    faq_markup_from_graph: str
    types: str
    structured_data: str


class _JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_jsonld_script = False
        self._buffer = StringIO()
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attrs_map = {k.lower(): (v or "") for k, v in attrs}
        script_type = attrs_map.get("type", "").strip().lower()
        if script_type.startswith("application/ld+json"):
            self._in_jsonld_script = True
            self._buffer = StringIO()

    def handle_data(self, data: str) -> None:
        if self._in_jsonld_script:
            self._buffer.write(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or not self._in_jsonld_script:
            return
        self._in_jsonld_script = False
        payload = self._buffer.getvalue().strip()
        if payload:
            self.blocks.append(payload)


def create_structured_data_inventory_from_ingestion(
    *,
    source_bundle: Mapping[str, Any],
    api_key: str,
    output_csv: str | Path | None = None,
    base_url: str = "https://api.wordlift.io",
    ssl_ca_cert: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> pd.DataFrame:
    """Build a structured-data inventory table from shared ingestion settings."""

    ingest_config = _normalize_source_bundle(source_bundle)
    source_result = resolve_ingestion_source_items(ingest_config)
    total = len(source_result.items)
    completed = 0

    def _on_ingest_event(payload: dict[str, Any]) -> None:
        nonlocal completed
        if on_progress is None:
            return
        event_name = str(payload.get("event") or "")
        if event_name == "ingest.item_loaded":
            status = "ok"
        elif event_name == "ingest.item_failed":
            status = "error"
        else:
            return
        completed += 1
        url = str(payload.get("url") or "")
        on_progress(
            {
                "event": "inventory.progress.updated",
                "timestamp": _utc_now_iso(),
                "meta": {
                    "total": total,
                    "completed": completed,
                    "remaining": max(total - completed, 0),
                    "url": url,
                    "status": status,
                },
            }
        )

    if on_progress is not None:
        on_progress(
            {
                "event": "inventory.progress.started",
                "timestamp": _utc_now_iso(),
                "meta": {"total": total},
            }
        )

    ingestion_result = create_orchestrator(emit=_on_ingest_event).run_with_items(
        source_result.resolved,
        source_result.items,
    )
    dataset_uri = _get_dataset_uri(
        api_key=api_key,
        base_url=base_url,
        ssl_ca_cert=ssl_ca_cert,
    )

    loaded_by_item = {page.item_id: page for page in ingestion_result.pages}
    rows: list[StructuredDataInventoryRow] = []

    for item in source_result.items:
        page = loaded_by_item.get(item.id)
        url = item.url
        if page is None:
            row = _empty_row(url=url)
        else:
            url = page.final_url or page.url
            try:
                row = _build_inventory_row(
                    url=url, html=page.html, dataset_uri=dataset_uri
                )
            except Exception:
                row = _empty_row(url=url)
        rows.append(row)

    data = [asdict(row) for row in rows]
    result = pd.DataFrame(
        data,
        columns=[
            "url",
            "faq_markup",
            "faq_markup_from_graph",
            "types",
            "structured_data",
        ],
    )
    if output_csv is not None:
        result.to_csv(output_csv, index=False)
    if on_progress is not None:
        on_progress(
            {
                "event": "inventory.progress.completed",
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


def _get_dataset_uri(*, api_key: str, base_url: str, ssl_ca_cert: str | None) -> str:
    return StructuredDataEngine().get_dataset_uri(
        api_key=api_key,
        base_url=base_url,
        ssl_ca_cert=ssl_ca_cert,
    )


def _empty_row(*, url: str) -> StructuredDataInventoryRow:
    return StructuredDataInventoryRow(
        url=url,
        faq_markup="no",
        faq_markup_from_graph="no",
        types="",
        structured_data=json.dumps({"@context": "https://schema.org", "@graph": []}),
    )


def _build_inventory_row(
    *, url: str, html: str, dataset_uri: str
) -> StructuredDataInventoryRow:
    blocks = _extract_jsonld_blocks(html)
    combined = _combine_jsonld_graph(blocks)
    nodes = combined["@graph"]
    types = _collect_types(nodes)
    faq_markup, faq_markup_from_graph = _has_faq_from_dataset(nodes, dataset_uri)

    return StructuredDataInventoryRow(
        url=url,
        faq_markup="yes" if faq_markup else "no",
        faq_markup_from_graph="yes" if faq_markup_from_graph else "no",
        types=",".join(types),
        structured_data=json.dumps(combined, ensure_ascii=False, separators=(",", ":")),
    )


def _extract_jsonld_blocks(html: str) -> list[Any]:
    parser = _JsonLdScriptParser()
    parser.feed(html)
    parsed: list[Any] = []
    for block in parser.blocks:
        try:
            parsed.append(json.loads(block))
        except Exception:
            continue
    return parsed


def _combine_jsonld_graph(blocks: list[Any]) -> dict[str, Any]:
    graph: list[dict[str, Any]] = []
    for block in blocks:
        graph.extend(_extract_graph_nodes(block))
    return {"@context": "https://schema.org", "@graph": graph}


def _extract_graph_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    stack: list[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(reversed(current))
            continue
        if not isinstance(current, dict):
            continue
        graph_value = current.get("@graph")
        if isinstance(graph_value, list):
            stack.extend(reversed(graph_value))
            node = {k: v for k, v in current.items() if k not in {"@graph", "@context"}}
            if node:
                nodes.append(node)
            continue
        nodes.append(current)
    return nodes


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strip_schema_prefix(type_name: str) -> str:
    value = type_name.strip()
    for prefix in ("http://schema.org/", "https://schema.org/", "schema.org/"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _collect_types(nodes: Iterable[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        for raw_type in _as_list(node.get("@type")):
            if not isinstance(raw_type, str):
                continue
            type_name = _strip_schema_prefix(raw_type)
            if not type_name or type_name in seen:
                continue
            seen.add(type_name)
            out.append(type_name)
    return out


def _is_faq_page_node(node: dict[str, Any]) -> bool:
    for raw_type in _as_list(node.get("@type")):
        if isinstance(raw_type, str) and _strip_schema_prefix(raw_type) == "FAQPage":
            return True
    return False


def _normalize_dataset_prefixes(dataset_uri: str) -> list[str]:
    base = dataset_uri.rstrip("/")
    prefixes = {dataset_uri, base, f"{base}/"}
    return sorted(p for p in prefixes if p)


def _has_faq_from_dataset(
    nodes: Iterable[dict[str, Any]],
    dataset_uri: str,
) -> tuple[bool, bool]:
    prefixes = _normalize_dataset_prefixes(dataset_uri)
    faq_found = False
    faq_from_graph = False
    for node in nodes:
        if not _is_faq_page_node(node):
            continue
        faq_found = True
        faq_id = node.get("@id")
        if isinstance(faq_id, str) and any(
            faq_id.startswith(prefix) for prefix in prefixes
        ):
            faq_from_graph = True
    return faq_found, faq_from_graph


__all__ = [
    "StructuredDataInventoryRow",
    "create_structured_data_inventory_from_ingestion",
]

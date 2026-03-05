from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from collections.abc import Mapping
from typing import Any, Callable

from .factory import create_orchestrator
from .factory import create_source_registry
from .models import SourceItem
from .orchestrator import IngestionResult
from .resolver import (
    ResolvedIngestionConfig,
    resolve_ingestion_config_from_mapping,
    resolve_ingestion_config_from_provider,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SourceResolutionResult:
    items: list[SourceItem]
    events: list[dict[str, Any]]
    resolved: ResolvedIngestionConfig


def run_ingestion(
    config_or_provider: Mapping[str, Any] | Any,
    *,
    emit: Callable[[dict[str, Any]], None] | None = None,
    fail_fast: bool = False,
) -> IngestionResult:
    if isinstance(config_or_provider, Mapping):
        resolved = resolve_ingestion_config_from_mapping(config_or_provider)
    else:
        resolved = resolve_ingestion_config_from_provider(config_or_provider)

    orchestrator = create_orchestrator(emit=emit, fail_fast=fail_fast)
    return orchestrator.run(resolved)


def resolve_ingestion_source_items(
    config_or_provider: Mapping[str, Any] | Any,
    *,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> SourceResolutionResult:
    if isinstance(config_or_provider, Mapping):
        resolved = resolve_ingestion_config_from_mapping(config_or_provider)
    else:
        resolved = resolve_ingestion_config_from_provider(config_or_provider)

    events: list[dict[str, Any]] = []
    items: list[SourceItem] = []
    skipped_by_regex = 0
    url_pattern: re.Pattern[str] | None = None
    if resolved.url_regex:
        url_pattern = re.compile(resolved.url_regex)

    def _emit(payload: dict[str, Any]) -> None:
        events.append(payload)
        if emit is not None:
            emit(payload)

    for warning in resolved.warnings:
        _emit(warning.to_event())

    source = create_source_registry().resolve(resolved.source_name)
    for item in source.iter_items(resolved):
        if url_pattern is not None and not url_pattern.search(item.url):
            skipped_by_regex += 1
            continue
        items.append(item)

    _emit(
        {
            "event": "ingest.source_summary",
            "timestamp": _utc_now_iso(),
            "source": resolved.source_name,
            "requested_loader": resolved.loader_name,
            "effective_loader": resolved.loader_name,
            "meta": {
                "resolved": len(items),
                "skipped_by_url_regex": skipped_by_regex,
                "total": len(items) + skipped_by_regex,
            },
        }
    )

    return SourceResolutionResult(items=items, events=events, resolved=resolved)


__all__ = ["SourceResolutionResult", "resolve_ingestion_source_items", "run_ingestion"]

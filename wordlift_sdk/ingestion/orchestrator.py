from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable

from .errors import IngestionConfigError, IngestionError
from .models import LoadedPage
from .registry import AdapterRegistry
from .resolver import ResolvedIngestionConfig


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IngestionResult:
    pages: list[LoadedPage]
    events: list[dict[str, Any]]


class IngestionOrchestrator:
    def __init__(
        self,
        *,
        source_registry: AdapterRegistry[Any],
        loader_registry: AdapterRegistry[Any],
        emit: Callable[[dict[str, Any]], None] | None = None,
        fail_fast: bool = False,
    ) -> None:
        self._source_registry = source_registry
        self._loader_registry = loader_registry
        self._emit = emit
        self._fail_fast = fail_fast

    def run(self, config: ResolvedIngestionConfig) -> IngestionResult:
        events: list[dict[str, Any]] = []
        pages: list[LoadedPage] = []
        failed = 0
        url_pattern: re.Pattern[str] | None = None
        if config.url_regex:
            try:
                url_pattern = re.compile(config.url_regex)
            except re.error as exc:
                raise IngestionConfigError(
                    "Invalid URL_REGEX pattern.",
                    code="INGEST_CFG_INVALID_URL_REGEX",
                    details={"url_regex": config.url_regex},
                ) from exc

        def emit(payload: dict[str, Any]) -> None:
            events.append(payload)
            if self._emit is not None:
                self._emit(payload)

        for warning in config.warnings:
            emit(warning.to_event())

        source = self._source_registry.resolve(config.source_name)
        configured_loader = config.loader_name

        for item in source.iter_items(config):
            if url_pattern is not None and not url_pattern.search(item.url):
                continue
            effective_loader = configured_loader
            if config.passthrough_when_html and item.html:
                effective_loader = "passthrough"

            emit(
                {
                    "event": "ingest.item_started",
                    "item_id": item.id,
                    "url": item.url,
                    "source": config.source_name,
                    "requested_loader": configured_loader,
                    "effective_loader": effective_loader,
                    "timestamp": _utc_now_iso(),
                    "meta": {},
                }
            )

            loader = self._loader_registry.resolve(effective_loader)
            try:
                page = loader.load(item, config)
                pages.append(page)
                emit(
                    {
                        "event": "ingest.item_loaded",
                        "item_id": item.id,
                        "url": item.url,
                        "source": config.source_name,
                        "requested_loader": configured_loader,
                        "effective_loader": effective_loader,
                        "timestamp": _utc_now_iso(),
                        "meta": {
                            "status_code": page.status_code,
                            "final_url": page.final_url,
                            "fetch_meta": page.fetch_meta,
                        },
                    }
                )
            except IngestionError as exc:
                failed += 1
                emit(
                    {
                        "event": "ingest.item_failed",
                        "item_id": item.id,
                        "url": item.url,
                        "source": config.source_name,
                        "requested_loader": configured_loader,
                        "effective_loader": effective_loader,
                        "timestamp": _utc_now_iso(),
                        "code": exc.code,
                        "message": str(exc),
                        "retryable": exc.retryable,
                        "meta": dict(exc.details),
                    }
                )
                if self._fail_fast:
                    raise
            except Exception as exc:  # pragma: no cover
                failed += 1
                emit(
                    {
                        "event": "ingest.item_failed",
                        "item_id": item.id,
                        "url": item.url,
                        "source": config.source_name,
                        "requested_loader": configured_loader,
                        "effective_loader": effective_loader,
                        "timestamp": _utc_now_iso(),
                        "code": "INGEST_ORCH_INTERNAL_ERROR",
                        "message": str(exc),
                        "retryable": False,
                        "meta": {},
                    }
                )
                if self._fail_fast:
                    raise

        emit(
            {
                "event": "ingest.summary",
                "timestamp": _utc_now_iso(),
                "source": config.source_name,
                "requested_loader": configured_loader,
                "effective_loader": configured_loader,
                "meta": {
                    "total": len(pages) + failed,
                    "loaded": len(pages),
                    "failed": failed,
                },
            }
        )
        return IngestionResult(pages=pages, events=events)


__all__ = ["IngestionOrchestrator", "IngestionResult"]

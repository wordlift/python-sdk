from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from .factory import create_orchestrator
from .orchestrator import IngestionResult
from .resolver import (
    resolve_ingestion_config_from_mapping,
    resolve_ingestion_config_from_provider,
)


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


__all__ = ["run_ingestion"]

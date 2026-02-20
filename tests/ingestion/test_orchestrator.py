from __future__ import annotations

from typing import Iterator

from wordlift_sdk.ingestion.errors import LoaderRuntimeError
from wordlift_sdk.ingestion.events import IngestionWarning
from wordlift_sdk.ingestion.models import LoadedPage, SourceItem
from wordlift_sdk.ingestion.orchestrator import IngestionOrchestrator
from wordlift_sdk.ingestion.registry import AdapterRegistry
from wordlift_sdk.ingestion.resolver import ResolvedIngestionConfig


class _Source:
    def __init__(self, items: list[SourceItem]) -> None:
        self._items = items

    def iter_items(self, config: ResolvedIngestionConfig) -> Iterator[SourceItem]:
        del config
        for item in self._items:
            yield item


class _Loader:
    def __init__(self, backend: str) -> None:
        self.backend = backend

    def load(self, item: SourceItem, config: ResolvedIngestionConfig) -> LoadedPage:
        del config
        return LoadedPage(
            item_id=item.id,
            url=item.url,
            final_url=item.url,
            status_code=200,
            html=item.html or "<html></html>",
            fetch_meta={"backend": self.backend},
        )


class _FailingLoader:
    def load(self, item: SourceItem, config: ResolvedIngestionConfig) -> LoadedPage:
        del item, config
        raise LoaderRuntimeError(
            "boom", code="INGEST_LOAD_NETWORK_ERROR", retryable=True
        )


def _config(**kwargs) -> ResolvedIngestionConfig:
    defaults = {
        "source_name": "urls",
        "loader_name": "simple",
        "passthrough_when_html": True,
        "timeout_ms": 30000,
        "retry_attempts": 5,
        "retry_backoff_ms": 2000,
        "source_config": {},
        "loader_config": {},
        "warnings": tuple(),
    }
    defaults.update(kwargs)
    return ResolvedIngestionConfig(**defaults)


def test_passthrough_precedence_when_embedded_html_present() -> None:
    source_registry: AdapterRegistry[object] = AdapterRegistry(kind="source")
    source_registry.register(
        "urls",
        _Source(
            [
                SourceItem(id="1", url="https://example.com/1", html="<html>1</html>"),
                SourceItem(id="2", url="https://example.com/2", html=None),
            ]
        ),
    )

    loader_registry: AdapterRegistry[object] = AdapterRegistry(kind="loader")
    loader_registry.register("simple", _Loader("simple"))
    loader_registry.register("passthrough", _Loader("passthrough"))

    orchestrator = IngestionOrchestrator(
        source_registry=source_registry,
        loader_registry=loader_registry,
    )
    result = orchestrator.run(_config(loader_name="simple", passthrough_when_html=True))

    assert len(result.pages) == 2
    assert result.pages[0].fetch_meta["backend"] == "passthrough"
    assert result.pages[1].fetch_meta["backend"] == "simple"


def test_item_failure_emits_structured_error_event() -> None:
    source_registry: AdapterRegistry[object] = AdapterRegistry(kind="source")
    source_registry.register(
        "urls", _Source([SourceItem(id="1", url="https://example.com/1")])
    )

    loader_registry: AdapterRegistry[object] = AdapterRegistry(kind="loader")
    loader_registry.register("simple", _FailingLoader())
    loader_registry.register("passthrough", _Loader("passthrough"))

    orchestrator = IngestionOrchestrator(
        source_registry=source_registry,
        loader_registry=loader_registry,
    )
    result = orchestrator.run(
        _config(loader_name="simple", passthrough_when_html=False)
    )

    assert len(result.pages) == 0
    failed = [e for e in result.events if e["event"] == "ingest.item_failed"]
    assert len(failed) == 1
    assert failed[0]["code"] == "INGEST_LOAD_NETWORK_ERROR"
    assert failed[0]["retryable"] is True


def test_warning_event_shape_is_machine_parseable() -> None:
    source_registry: AdapterRegistry[object] = AdapterRegistry(kind="source")
    source_registry.register("urls", _Source([]))
    loader_registry: AdapterRegistry[object] = AdapterRegistry(kind="loader")
    loader_registry.register("simple", _Loader("simple"))
    loader_registry.register("passthrough", _Loader("passthrough"))

    cfg = _config(
        warnings=(
            IngestionWarning(
                code="INGEST_CFG_CONFLICT",
                message="conflict",
                new_key="INGEST_LOADER",
                new_value="simple",
                legacy_key="WEB_PAGE_IMPORT_MODE",
                legacy_value="default",
                winner="INGEST_LOADER",
            ),
        )
    )
    orchestrator = IngestionOrchestrator(
        source_registry=source_registry,
        loader_registry=loader_registry,
    )
    result = orchestrator.run(cfg)

    warnings = [e for e in result.events if e["event"] == "ingest.warning"]
    assert len(warnings) == 1
    assert warnings[0]["new_key"] == "INGEST_LOADER"
    assert warnings[0]["legacy_key"] == "WEB_PAGE_IMPORT_MODE"
    assert warnings[0]["winner"] == "INGEST_LOADER"

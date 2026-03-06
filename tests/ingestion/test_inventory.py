from __future__ import annotations

import json

from wordlift_sdk.ingestion.api import SourceResolutionResult
from wordlift_sdk.ingestion.factory import create_source_registry
from wordlift_sdk.ingestion.inventory import (
    _as_list,
    _collect_types,
    _extract_graph_nodes,
    _extract_jsonld_blocks,
    _get_dataset_uri,
    _has_faq_from_dataset,
    _is_faq_page_node,
    _strip_schema_prefix,
    create_structured_data_inventory_from_ingestion,
)
from wordlift_sdk.ingestion.models import LoadedPage, SourceItem
from wordlift_sdk.ingestion.orchestrator import IngestionResult
from wordlift_sdk.ingestion.registry import AdapterRegistry
from wordlift_sdk.ingestion.resolver import ResolvedIngestionConfig


def _resolved_config() -> ResolvedIngestionConfig:
    return ResolvedIngestionConfig(
        source_name="urls",
        loader_name="simple",
        passthrough_when_html=True,
        timeout_ms=30000,
        retry_attempts=5,
        retry_backoff_ms=2000,
        source_config={},
        loader_config={},
        url_regex=None,
        warnings=tuple(),
    )


def test_create_structured_data_inventory_from_ingestion_builds_rows(
    monkeypatch,
) -> None:
    source_items = [
        SourceItem(id="u:1", url="https://example.com/a"),
        SourceItem(id="u:2", url="https://example.com/b"),
    ]
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=source_items,
            events=[],
            resolved=_resolved_config(),
        ),
    )

    class _Orchestrator:
        def run_with_items(self, _resolved, _items):
            return IngestionResult(
                pages=[
                    LoadedPage(
                        item_id="u:2",
                        url="https://example.com/b",
                        final_url=None,
                        status_code=200,
                        html=(
                            "<script type='application/ld+json'>"
                            '{"@type":"FAQPage","@id":"https://dataset.example/page#faq"}'
                            "</script>"
                        ),
                        fetch_meta={},
                    )
                ],
                events=[],
            )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a", "https://example.com/b"],
        },
        api_key="key",
    )

    assert list(df["url"]) == ["https://example.com/a", "https://example.com/b"]
    assert list(df["faq_markup"]) == ["no", "yes"]
    assert list(df["faq_markup_from_graph"]) == ["no", "yes"]
    assert list(df["types"]) == ["", "FAQPage"]
    assert json.loads(df.iloc[0]["structured_data"]) == {
        "@context": "https://schema.org",
        "@graph": [],
    }


def test_create_structured_data_inventory_from_ingestion_writes_csv(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=[SourceItem(id="u:1", url="https://example.com/a")],
            events=[],
            resolved=_resolved_config(),
        ),
    )

    class _Orchestrator:
        def run_with_items(self, _resolved, _items):
            return IngestionResult(
                pages=[
                    LoadedPage(
                        item_id="u:1",
                        url="https://example.com/a",
                        final_url="https://example.com/a?final=1",
                        status_code=200,
                        html="<html/>",
                        fetch_meta={},
                    )
                ],
                events=[],
            )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    output = tmp_path / "inventory.csv"
    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a"],
        },
        api_key="key",
        output_csv=output,
    )
    assert output.exists()
    assert df.iloc[0]["url"] == "https://example.com/a?final=1"


def test_create_structured_data_inventory_from_ingestion_emits_progress_events(
    monkeypatch,
) -> None:
    source_items = [
        SourceItem(id="u:1", url="https://example.com/a"),
        SourceItem(id="u:2", url="https://example.com/b"),
    ]
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=source_items,
            events=[],
            resolved=_resolved_config(),
        ),
    )

    class _Orchestrator:
        def __init__(self, emit):
            self._emit = emit

        def run_with_items(self, _resolved, items):
            selected = list(items)
            self._emit(
                {
                    "event": "ingest.item_loaded",
                    "url": selected[0].url,
                    "meta": {},
                }
            )
            self._emit(
                {
                    "event": "ingest.item_failed",
                    "url": selected[1].url,
                    "meta": {},
                }
            )
            return IngestionResult(
                pages=[
                    LoadedPage(
                        item_id="u:1",
                        url="https://example.com/a",
                        final_url=None,
                        status_code=200,
                        html="<html/>",
                        fetch_meta={},
                    ),
                ],
                events=[],
            )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(emit),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    events: list[dict[str, object]] = []
    create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a", "https://example.com/b"],
        },
        api_key="key",
        on_progress=events.append,
    )

    assert [event["event"] for event in events] == [
        "inventory.progress.started",
        "inventory.progress.updated",
        "inventory.progress.updated",
        "inventory.progress.completed",
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
        "url": "https://example.com/b",
        "status": "error",
    }
    assert events[3]["meta"] == {"total": 2, "completed": 2}


def test_create_structured_data_inventory_progress_starts_during_ingestion(
    monkeypatch,
) -> None:
    source_items = [SourceItem(id="u:1", url="https://example.com/a")]
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=source_items,
            events=[],
            resolved=_resolved_config(),
        ),
    )

    class _Orchestrator:
        def __init__(self, emit):
            self._emit = emit

        def run_with_items(self, _resolved, _items):
            self._emit({"event": "ingest.item_loaded", "url": "https://example.com/a"})
            return IngestionResult(
                pages=[
                    LoadedPage(
                        item_id="u:1",
                        url="https://example.com/a",
                        final_url=None,
                        status_code=200,
                        html="<html/>",
                        fetch_meta={},
                    )
                ],
                events=[],
            )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(emit),
    )
    events: list[dict[str, object]] = []

    def _dataset_uri(**_kwargs):
        assert any(
            event["event"] == "inventory.progress.updated" for event in events
        ), "progress update should be emitted during ingestion before row building"
        return "https://dataset.example"

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri", _dataset_uri
    )

    create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a"],
        },
        api_key="key",
        on_progress=events.append,
    )


def test_create_structured_data_inventory_zero_items_progress_lifecycle(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=[],
            events=[],
            resolved=_resolved_config(),
        ),
    )

    class _Orchestrator:
        def run_with_items(self, _resolved, items):
            assert list(items) == []
            return IngestionResult(pages=[], events=[])

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    events: list[dict[str, object]] = []
    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": [],
        },
        api_key="key",
        on_progress=events.append,
    )

    assert df.empty
    assert [event["event"] for event in events] == [
        "inventory.progress.started",
        "inventory.progress.completed",
    ]
    assert events[0]["meta"] == {"total": 0}
    assert events[1]["meta"] == {"total": 0, "completed": 0}


def test_create_structured_data_inventory_uses_single_source_pass(
    monkeypatch,
) -> None:
    class _CountingSource:
        def __init__(self) -> None:
            self.calls = 0

        def iter_items(self, _config):
            self.calls += 1
            yield SourceItem(id="u:1", url="https://example.com/a")

    counting_source = _CountingSource()
    registry: AdapterRegistry[object] = create_source_registry()
    registry.register("urls", counting_source)
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.api.create_source_registry", lambda: registry
    )

    class _Orchestrator:
        def run_with_items(self, _resolved, items):
            pages = [
                LoadedPage(
                    item_id=item.id,
                    url=item.url,
                    final_url=None,
                    status_code=200,
                    html="<html/>",
                    fetch_meta={},
                )
                for item in items
            ]
            return IngestionResult(pages=pages, events=[])

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://ignored.example"],
        },
        api_key="key",
    )

    assert counting_source.calls == 1
    assert list(df["url"]) == ["https://example.com/a"]


def test_create_structured_data_inventory_falls_back_to_empty_row_on_build_error(
    monkeypatch,
) -> None:
    source_items = [SourceItem(id="u:1", url="https://example.com/a")]
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=source_items,
            events=[],
            resolved=_resolved_config(),
        ),
    )

    class _Orchestrator:
        def run_with_items(self, _resolved, _items):
            return IngestionResult(
                pages=[
                    LoadedPage(
                        item_id="u:1",
                        url="https://example.com/a",
                        final_url=None,
                        status_code=200,
                        html="<html/>",
                        fetch_meta={},
                    )
                ],
                events=[],
            )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._build_inventory_row",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a"],
        },
        api_key="key",
    )

    assert df.iloc[0]["faq_markup"] == "no"
    assert df.iloc[0]["faq_markup_from_graph"] == "no"


def test_create_structured_data_inventory_ignores_ingest_events_without_progress_callback(
    monkeypatch,
) -> None:
    source_items = [SourceItem(id="u:1", url="https://example.com/a")]
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.resolve_ingestion_source_items",
        lambda _cfg: SourceResolutionResult(
            items=source_items,
            events=[],
            resolved=_resolved_config(),
        ),
    )

    class _Orchestrator:
        def __init__(self, emit):
            self._emit = emit

        def run_with_items(self, _resolved, _items):
            self._emit({"event": "ingest.item_loaded", "url": "https://example.com/a"})
            self._emit({"event": "ingest.summary"})
            return IngestionResult(
                pages=[
                    LoadedPage(
                        item_id="u:1",
                        url="https://example.com/a",
                        final_url=None,
                        status_code=200,
                        html="<html/>",
                        fetch_meta={},
                    )
                ],
                events=[],
            )

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.create_orchestrator",
        lambda emit=None, fail_fast=False: _Orchestrator(emit),
    )
    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory._get_dataset_uri",
        lambda **_kwargs: "https://dataset.example",
    )

    df = create_structured_data_inventory_from_ingestion(
        source_bundle={
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/a"],
        },
        api_key="key",
    )

    assert list(df["url"]) == ["https://example.com/a"]


def test_inventory_helper_branches(monkeypatch) -> None:
    blocks = _extract_jsonld_blocks(
        '<script type=\'application/ld+json\'>{"@type":"FAQPage"}</script>'
        "<script type='application/ld+json'>{not-json}</script>"
    )
    assert blocks == [{"@type": "FAQPage"}]

    nodes = _extract_graph_nodes(
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "FAQPage", "@id": "https://dataset.example/page#faq"},
                {
                    "@graph": [{"@type": ["Article", 1, "Article"]}],
                    "@context": "x",
                    "name": "outer",
                },
                "ignore-me",
            ],
        }
    )
    assert any(node.get("@type") == "FAQPage" for node in nodes)
    assert any(node.get("name") == "outer" for node in nodes)

    assert _as_list(None) == []
    assert _as_list(["a"]) == ["a"]
    assert _as_list("a") == ["a"]
    assert _strip_schema_prefix("https://schema.org/FAQPage") == "FAQPage"
    assert _strip_schema_prefix("PlainType") == "PlainType"

    assert _collect_types(nodes) == ["FAQPage", "Article"]
    assert _is_faq_page_node({"@type": "FAQPage"}) is True
    assert _is_faq_page_node({"@type": "Article"}) is False
    assert _has_faq_from_dataset(nodes, "https://dataset.example") == (True, True)

    class _Engine:
        def get_dataset_uri(self, **kwargs):
            return f"ok:{kwargs['api_key']}"

    monkeypatch.setattr(
        "wordlift_sdk.ingestion.inventory.StructuredDataEngine", _Engine
    )
    assert _get_dataset_uri(api_key="k", base_url="b", ssl_ca_cert=None) == "ok:k"

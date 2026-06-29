from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from wordlift_sdk.graph.audit import (
    GraphKpiSnapshotOptions,
    build_graph_kpi_api_payload,
    calculate_graph_kpi_snapshot,
)


def _write_graph(path: Path) -> None:
    path.write_text(
        """
        @prefix schema: <http://schema.org/> .
        @prefix data: <https://data.example.com/dataset/> .

        data:page-a
          a schema:Product ;
          schema:url "https://www.example.com/a" ;
          schema:name "A" ;
          schema:brand data:brand-a .

        data:brand-a
          a schema:Brand ;
          schema:name "Brand A" .

        data:page-b
          a schema:Product ;
          schema:url "https://www.example.com/b" ;
          schema:brand data:brand-missing .

        data:page-b-duplicate
          a schema:Product ;
          schema:url "https://www.example.com/b" .

        data:orphan
          a schema:Thing ;
          schema:name "Orphan" .
        """,
        encoding="utf-8",
    )


def _write_shape(path: Path) -> None:
    path.write_text(
        """
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix schema: <http://schema.org/> .

        <urn:ProductNameShape>
          a sh:NodeShape ;
          sh:targetClass schema:Product ;
          sh:property [
            sh:path schema:name ;
            sh:minCount 1 ;
            sh:message "Product must have a name." ;
          ] .
        """,
        encoding="utf-8",
    )


def test_calculate_graph_kpi_snapshot_includes_fast_counts_and_compliance(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "graph.ttl"
    shape_path = tmp_path / "shape.ttl"
    _write_graph(graph_path)
    _write_shape(shape_path)

    snapshot = calculate_graph_kpi_snapshot(
        graph_path,
        GraphKpiSnapshotOptions(
            website_host="www.example.com",
            graph_hosts={"data.example.com"},
            builtin_shapes=["schemaorg-grammar"],
            extra_shapes=[str(shape_path)],
            shacl_workers=1,
        ),
    )

    assert snapshot["totals"]["total_entity_count"] == 5
    assert snapshot["totals"]["unique_urls_within_website_scope"] == 2
    assert snapshot["entity_type_counts"]["Product"] == 3
    assert snapshot["property_counts"]["schema:url"] == 3
    assert snapshot["rich_snippet_candidate_entities"]["by_type"]["Product"] == 3
    assert snapshot["integrity"]["duplicate_url_group_count"] == 1
    assert snapshot["integrity"]["broken_internal_edge_count"] == 1
    assert snapshot["connectivity"]["orphan_entity_count"] == 2

    compliance = snapshot["schema_compliance"]
    assert compliance["urls_checked"] == 2
    assert compliance["urls_with_errors"] == 1
    assert compliance["errors"] == 2


def test_build_graph_kpi_api_payload_is_numeric_except_snapshot_metadata(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "graph.ttl"
    shape_path = tmp_path / "shape.ttl"
    _write_graph(graph_path)
    _write_shape(shape_path)
    snapshot = calculate_graph_kpi_snapshot(
        graph_path,
        GraphKpiSnapshotOptions(
            website_host="www.example.com",
            graph_hosts={"data.example.com"},
            builtin_shapes=["schemaorg-grammar"],
            extra_shapes=[str(shape_path)],
            shacl_workers=1,
        ),
    )

    payload = build_graph_kpi_api_payload(
        snapshot,
        snapshot_date="2026-06-29",
        calculated_at=datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc),
    )

    assert payload["snapshot_date"] == "2026-06-29"
    assert payload["calculated_at"] == "2026-06-29T10:00:00Z"
    assert payload["snapshot_origin"] == "worai_graph_kpis"
    assert payload["schema_compliance"]["urls_checked"] == 2
    assert payload["schema_compliance"]["errors"] == 2
    assert "orphan_entity_examples" not in payload
    assert "broken_internal_edge_examples" not in payload

    def assert_numeric_kpis(value, path: str = "") -> None:
        if path in {"snapshot_date", "calculated_at", "snapshot_origin"}:
            assert isinstance(value, str)
            return
        if isinstance(value, dict):
            for key, child in value.items():
                assert_numeric_kpis(child, key)
            return
        assert isinstance(value, (int, float))
        assert value >= 0

    assert_numeric_kpis(payload)


def test_build_graph_kpi_api_payload_rejects_non_numeric_kpi_values() -> None:
    with pytest.raises(ValueError):
        build_graph_kpi_api_payload(
            {
                "totals": {"total_triples": 1},
                "entity_type_counts": {"Thing": "not numeric"},
            },
            snapshot_date="2026-06-29",
        )

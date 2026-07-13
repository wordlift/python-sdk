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


def _write_ntriples_graph(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "<https://data.example.com/dataset/page-a> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Product> .",
                '<https://data.example.com/dataset/page-a> <http://schema.org/url> "https://www.example.com/a" .',
                '<https://data.example.com/dataset/page-a> <http://schema.org/name> "A" .',
                "<https://data.example.com/dataset/page-a> <http://schema.org/brand> <https://data.example.com/dataset/brand-a> .",
                "<https://data.example.com/dataset/brand-a> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Brand> .",
                '<https://data.example.com/dataset/brand-a> <http://schema.org/name> "Brand A" .',
                "<https://data.example.com/dataset/page-b> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Product> .",
                '<https://data.example.com/dataset/page-b> <http://schema.org/url> "https://www.example.com/b" .',
                "<https://data.example.com/dataset/page-b> <http://schema.org/brand> <https://data.example.com/dataset/brand-missing> .",
                "<https://data.example.com/dataset/page-b-duplicate> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Product> .",
                '<https://data.example.com/dataset/page-b-duplicate> <http://schema.org/url> "https://www.example.com/b" .',
                "<https://data.example.com/dataset/orphan> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Thing> .",
                '<https://data.example.com/dataset/orphan> <http://schema.org/name> "Orphan" .',
                "",
            ]
        ),
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


def test_streaming_graph_kpi_snapshot_matches_full_structural_counts(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "graph.nt"
    _write_ntriples_graph(graph_path)

    options = GraphKpiSnapshotOptions(
        website_host="www.example.com",
        graph_hosts={"data.example.com"},
        memory_mode="streaming",
    )
    snapshot = calculate_graph_kpi_snapshot(graph_path, options)

    assert snapshot["totals"]["total_entity_count"] == 5
    assert snapshot["totals"]["total_typed_entity_count"] == 5
    assert snapshot["totals"]["total_triples"] == 13
    assert snapshot["totals"]["total_property_count"] == 8
    assert snapshot["totals"]["unique_property_count"] == 3
    assert snapshot["totals"]["rdf_type_triples"] == 5
    assert snapshot["totals"]["unique_urls_within_website_scope"] == 2
    assert snapshot["entity_type_counts"]["Product"] == 3
    assert snapshot["property_counts"]["schema:url"] == 3
    assert snapshot["rich_snippet_candidate_entities"]["by_type"]["Product"] == 3
    assert snapshot["edges"]["total_internal_edges"] == 2
    assert snapshot["edges"]["edge_predicate_counts"]["schema:brand"] == 2
    assert snapshot["connectivity"]["orphan_entity_count"] == 2
    assert snapshot["integrity"]["broken_internal_edge_count"] == 1
    assert snapshot["integrity"]["duplicate_url_group_count"] == 1
    assert snapshot["integrity"]["duplicate_extra_entity_count"] == 1
    assert snapshot["topology"]["isolated_graph_count"] == 4
    assert snapshot["topology"]["largest_component_node_count"] == 2
    assert snapshot["schema_compliance"]["skipped"] == 1


def test_streaming_graph_kpi_snapshot_rejects_non_ntriples_input(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "graph.ttl"
    _write_graph(graph_path)

    with pytest.raises(ValueError, match=r"N-Triples \(\.nt\)"):
        calculate_graph_kpi_snapshot(
            graph_path,
            GraphKpiSnapshotOptions(memory_mode="streaming"),
        )


def test_streaming_graph_kpi_payload_marks_partial_snapshot(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.nt"
    _write_ntriples_graph(graph_path)
    snapshot = calculate_graph_kpi_snapshot(
        graph_path,
        GraphKpiSnapshotOptions(
            website_host="www.example.com",
            graph_hosts={"data.example.com"},
            memory_mode="streaming",
        ),
    )

    payload = build_graph_kpi_api_payload(snapshot, snapshot_date="2026-06-29")

    assert payload["all_total_entities"] == 5
    assert payload["all_unique_urls_count"] == 2
    assert payload["density_score"] == payload["all_edge_node_ratio"]
    assert payload["schema_compliance_skipped"] == 1
    assert payload["graph_health_score_partial"] == 1
    assert payload["schema_compliance_urls_checked"] == 0
    assert payload["rich_snippets_valid_count"] == 0
    assert payload["graph_health_score"] == 78


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
    assert payload["all_total_entities"] == 5
    assert payload["all_total_typed_entities"] == 5
    assert payload["all_total_triples"] == 13
    assert payload["all_total_properties"] == 8
    assert payload["all_unique_properties_count"] == 3
    assert payload["all_rdf_type_triples_count"] == 5
    assert payload["all_internal_nodes_count"] == 5
    assert payload["all_internal_edges_count"] == 2
    assert payload["all_edge_predicate_counts"]["schema:brand"] == 2
    assert payload["all_unique_urls_count"] == 2
    assert payload["all_orphans_count"] == 2
    assert payload["all_broken_links_count"] == 1
    assert payload["all_isolated_graphs_count"] == 4
    assert payload["all_largest_component_nodes_count"] == 2
    assert payload["all_duplicates_count"] == 1
    assert payload["all_duplicate_extra_entities_count"] == 1
    assert payload["rich_snippets_candidate_count"] == 3
    assert payload["rich_snippets_by_type"]["Product"] == 3
    assert payload["schema_compliance_errors"] == 2
    assert payload["schema_compliance_urls_checked"] == 2
    assert payload["schema_compliance_urls_with_errors"] == 1
    assert payload["graph_health_score"] == 43
    assert payload["all_entity_types"]["Product"] == 3
    assert payload["all_properties_by_predicate"]["schema:url"] == 3
    assert "orphan_entity_examples" not in payload
    assert "broken_internal_edge_examples" not in payload
    assert "total_entities" not in payload
    assert "total_triples" not in payload
    assert "internal_edges" not in payload
    assert "unique_urls_within_website_scope" not in payload
    assert "broken_internal_edges" not in payload
    assert "duplicate_url_groups" not in payload
    assert "schema_compliance" not in payload
    assert "entity_type_counts" not in payload
    assert "property_counts" not in payload
    assert "rich_snippet_candidate_entities" not in payload
    assert "public_total_entities" not in payload
    assert "private_total_entities" not in payload
    assert "public_internal_edges_count" not in payload
    assert "private_internal_edges_count" not in payload

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


def test_graph_health_score_is_normalized_by_metric_denominators() -> None:
    small_payload = build_graph_kpi_api_payload(
        {
            "totals": {
                "total_entity_count": 100,
                "total_property_count": 300,
                "total_triples": 1_000,
                "unique_urls_within_website_scope": 10,
            },
            "edges": {"total_internal_edges": 20},
            "integrity": {
                "broken_internal_edge_count": 2,
                "duplicate_url_group_count": 1,
            },
            "schema_compliance": {
                "urls_checked": 10,
                "errors": 1,
                "warnings": 2,
                "google_merchant_eligible": 8,
                "google_merchant_not_eligible": 2,
            },
        },
        snapshot_date="2026-06-29",
    )
    large_payload = build_graph_kpi_api_payload(
        {
            "totals": {
                "total_entity_count": 1_000,
                "total_property_count": 3_000,
                "total_triples": 10_000,
                "unique_urls_within_website_scope": 100,
            },
            "edges": {"total_internal_edges": 200},
            "integrity": {
                "broken_internal_edge_count": 20,
                "duplicate_url_group_count": 10,
            },
            "schema_compliance": {
                "urls_checked": 100,
                "errors": 10,
                "warnings": 20,
                "google_merchant_eligible": 80,
                "google_merchant_not_eligible": 20,
            },
        },
        snapshot_date="2026-06-29",
    )

    assert small_payload["graph_health_score"] == large_payload["graph_health_score"]
    assert small_payload["graph_health_score"] == 94


def test_graph_health_score_uses_safe_defaults_for_missing_denominators() -> None:
    payload = build_graph_kpi_api_payload(
        {
            "totals": {
                "total_entity_count": 10,
                "total_property_count": 20,
                "total_triples": 30,
            },
            "edges": {"total_internal_edges": 0},
            "integrity": {
                "broken_internal_edge_count": 5,
                "duplicate_url_group_count": 5,
            },
            "schema_compliance": {
                "urls_checked": 0,
                "errors": 5,
                "warnings": 5,
            },
        },
        snapshot_date="2026-06-29",
    )

    assert payload["graph_health_score"] == 100


def test_build_graph_kpi_api_payload_rejects_non_numeric_kpi_values() -> None:
    with pytest.raises(ValueError):
        build_graph_kpi_api_payload(
            {
                "totals": {"total_triples": 1},
                "entity_type_counts": {"Thing": "not numeric"},
            },
            snapshot_date="2026-06-29",
        )

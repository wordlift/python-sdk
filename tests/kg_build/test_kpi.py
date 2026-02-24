from rdflib import Graph, Literal, RDF, URIRef

from wordlift_sdk.kg_build.kpi import KgBuildKpiCollector


def test_kpi_collector_records_graph_and_validation() -> None:
    collector = KgBuildKpiCollector(
        dataset_uri="https://data.example.com/dataset", validation_enabled=True
    )
    graph = Graph()
    s = URIRef("https://data.example.com/dataset/entities/1")
    graph.add((s, RDF.type, URIRef("https://schema.org/Thing")))
    graph.add((s, URIRef("https://schema.org/name"), Literal("A")))

    collector.record_graph(graph)
    collector.record_validation(
        passed=False,
        warning_count=2,
        error_count=1,
        warning_sources={"google-article": 2},
        error_sources={"google-product": 1},
    )
    summary = collector.summary("demo")

    assert summary["totals"]["total_entities"] == 1
    assert summary["totals"]["type_assertions_total"] == 1
    assert summary["totals"]["property_assertions_total"] == 1
    assert summary["entities_by_type"] == {"https://schema.org/Thing": 1}
    assert summary["properties_by_predicate"] == {"https://schema.org/name": 1}
    assert summary["validation"] == {
        "total": 1,
        "pass": 0,
        "fail": 1,
        "warnings": {"count": 2, "sources": {"google-article": 2}},
        "errors": {"count": 1, "sources": {"google-product": 1}},
    }


def test_kpi_collector_graph_metrics_are_dataset_scoped() -> None:
    collector = KgBuildKpiCollector(dataset_uri="https://data.example.com/dataset")
    graph = Graph()
    in_scope = URIRef("https://data.example.com/dataset/entities/1")
    out_scope = URIRef("https://example.com/entities/2")
    graph.add((in_scope, RDF.type, URIRef("https://schema.org/Thing")))
    graph.add((in_scope, URIRef("https://schema.org/name"), Literal("A")))
    graph.add((out_scope, RDF.type, URIRef("https://schema.org/Thing")))

    assert collector.graph_metrics(graph) == {
        "entities": 1,
        "type_assertions": 1,
        "property_assertions": 1,
    }


def test_kpi_collector_validation_is_null_when_disabled() -> None:
    collector = KgBuildKpiCollector(dataset_uri="https://data.example.com/dataset")
    summary = collector.summary("demo")
    assert summary["validation"] is None

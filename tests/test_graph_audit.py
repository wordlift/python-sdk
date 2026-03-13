"""Tests for the graph audit module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from wordlift_sdk.graph.audit import (
    AuditOptions,
    GraphAuditor,
    load_graph,
)
from wordlift_sdk.graph.audit.kpis import (
    BrokenLinksKpi,
    DuplicatesKpi,
    EdgeNodeRatioKpi,
    EdgesKpi,
    EntityTypesKpi,
    IsolatedGraphsKpi,
    OrphansKpi,
    PropertiesKpi,
    RichSnippetsKpi,
    TotalsKpi,
    UniqueUrlsKpi,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCHEMA = "http://schema.org/"


def _g(*triples) -> Graph:
    g = Graph()
    for triple in triples:
        g.add(triple)
    return g


def _uri(local: str) -> URIRef:
    return URIRef(f"https://example.org/{local}")


def _schema(local: str) -> URIRef:
    return URIRef(f"{_SCHEMA}{local}")


@pytest.fixture()
def simple_graph() -> Graph:
    """One Article entity with schema:url and schema:name."""
    entity = _uri("article/1")
    return _g(
        (entity, RDF.type, _schema("Article")),
        (entity, _schema("url"), Literal("https://example.org/article/1")),
        (entity, _schema("name"), Literal("My Article")),
    )


@pytest.fixture()
def graph_with_children() -> Graph:
    """Entity with IRI-prefix children."""
    parent = _uri("entity/1")
    child = _uri("entity/1/part")
    return _g(
        (parent, RDF.type, _schema("Product")),
        (parent, _schema("url"), Literal("https://example.org/entity/1")),
        (parent, _schema("name"), Literal("Parent product")),
        (child, RDF.type, _schema("ProductGroup")),
        (child, _schema("name"), Literal("Child group")),
    )


@pytest.fixture()
def graph_with_duplicates() -> Graph:
    """Two distinct IRIs sharing the same schema:url."""
    url = Literal("https://example.org/page")
    return _g(
        (URIRef("https://data.example.org/a"), _schema("url"), url),
        (URIRef("https://data.example.org/b"), _schema("url"), url),
    )


@pytest.fixture()
def graph_with_broken_links() -> Graph:
    """An edge pointing to a non-existent subject."""
    entity = _uri("entity/1")
    dangling = _uri("entity/ghost")
    return _g(
        (entity, RDF.type, _schema("Person")),
        (entity, _schema("knows"), dangling),
    )


@pytest.fixture()
def disconnected_graph() -> Graph:
    """Two completely unrelated entities."""
    a = _uri("a")
    b = _uri("b")
    return _g(
        (a, RDF.type, _schema("Thing")),
        (b, RDF.type, _schema("Thing")),
    )


# ---------------------------------------------------------------------------
# _loader
# ---------------------------------------------------------------------------


def test_load_graph_turtle(tmp_path: Path) -> None:
    ttl = tmp_path / "g.ttl"
    ttl.write_text(
        textwrap.dedent(
            """\
            @prefix schema: <http://schema.org/> .
            <https://example.org/1> a schema:Article .
            """
        )
    )
    result = load_graph(ttl)
    assert len(result.errors) == 0
    assert len(result.graph) == 1


def test_load_graph_invalid_returns_error(tmp_path: Path) -> None:
    bad = tmp_path / "g.ttl"
    bad.write_text("this is not turtle!")
    result = load_graph(bad)
    assert len(result.errors) == 1
    assert result.errors[0].code == "parse_error"


# ---------------------------------------------------------------------------
# EntityTypesKpi
# ---------------------------------------------------------------------------


def test_entity_types(simple_graph: Graph) -> None:
    result = EntityTypesKpi().collect(simple_graph)
    assert result.by_type == {f"{_SCHEMA}Article": 1}


# ---------------------------------------------------------------------------
# PropertiesKpi
# ---------------------------------------------------------------------------


def test_properties(simple_graph: Graph) -> None:
    result = PropertiesKpi().collect(simple_graph)
    assert result.by_predicate[f"{_SCHEMA}url"] == 1
    assert result.by_predicate[f"{_SCHEMA}name"] == 1
    assert f"{RDF}type" not in result.by_predicate


# ---------------------------------------------------------------------------
# TotalsKpi
# ---------------------------------------------------------------------------


def test_totals(simple_graph: Graph) -> None:
    result = TotalsKpi().collect(simple_graph)
    assert result.total_entities == 1
    assert result.total_triples == 3
    assert result.total_properties == 2  # url + name


# ---------------------------------------------------------------------------
# UniqueUrlsKpi
# ---------------------------------------------------------------------------


def test_unique_urls(simple_graph: Graph) -> None:
    result = UniqueUrlsKpi().collect(simple_graph)
    assert result.count == 1
    assert result.urls == ["https://example.org/article/1"]


# ---------------------------------------------------------------------------
# EdgesKpi
# ---------------------------------------------------------------------------


def test_edges_counts_iri_objects() -> None:
    entity = _uri("a")
    target = _uri("b")
    g = _g(
        (entity, _schema("knows"), target),
        (entity, _schema("name"), Literal("Alice")),
    )
    result = EdgesKpi().collect(g)
    assert result.count == 1  # only the IRI object


# ---------------------------------------------------------------------------
# OrphansKpi
# ---------------------------------------------------------------------------


def test_orphans(simple_graph: Graph) -> None:
    result = OrphansKpi().collect(simple_graph)
    # The entity is never pointed to by anything → it is an orphan
    assert result.count == 1


def test_orphans_none_when_referenced() -> None:
    parent = _uri("parent")
    child = _uri("child")
    g = _g(
        (parent, _schema("hasPart"), child),
        (child, RDF.type, _schema("Thing")),
    )
    result = OrphansKpi().collect(g)
    # child appears as an object → not an orphan; parent is never an object → orphan
    assert str(child) not in result.iris


# ---------------------------------------------------------------------------
# BrokenLinksKpi
# ---------------------------------------------------------------------------


def test_broken_links(graph_with_broken_links: Graph) -> None:
    result = BrokenLinksKpi().collect(graph_with_broken_links)
    assert result.count == 1
    assert "entity/ghost" in result.iris[0]


def test_no_broken_links(simple_graph: Graph) -> None:
    result = BrokenLinksKpi().collect(simple_graph)
    assert result.count == 0


# ---------------------------------------------------------------------------
# IsolatedGraphsKpi
# ---------------------------------------------------------------------------


def test_isolated_graphs_count(disconnected_graph: Graph) -> None:
    result = IsolatedGraphsKpi().collect(disconnected_graph)
    assert result.component_count == 2
    assert result.components is None  # not requested


def test_isolated_graphs_with_list(disconnected_graph: Graph) -> None:
    result = IsolatedGraphsKpi(list_components=True).collect(disconnected_graph)
    assert result.component_count == 2
    assert result.components is not None
    assert len(result.components) == 2


def test_connected_graph_single_component() -> None:
    a, b = _uri("a"), _uri("b")
    g = _g((a, _schema("knows"), b), (b, RDF.type, _schema("Person")))
    result = IsolatedGraphsKpi().collect(g)
    assert result.component_count == 1


# ---------------------------------------------------------------------------
# EdgeNodeRatioKpi
# ---------------------------------------------------------------------------


def test_edge_node_ratio() -> None:
    a, b, c = _uri("a"), _uri("b"), _uri("c")
    g = _g(
        (a, _schema("knows"), b),
        (a, _schema("knows"), c),
        (b, _schema("knows"), c),
    )
    result = EdgeNodeRatioKpi().collect(g)
    # nodes = distinct subjects = a, b  (c has no outgoing triples)
    assert result.nodes == 2
    assert result.edges == 3
    assert result.ratio == 1.5


# ---------------------------------------------------------------------------
# DuplicatesKpi
# ---------------------------------------------------------------------------


def test_duplicates(graph_with_duplicates: Graph) -> None:
    result = DuplicatesKpi().collect(graph_with_duplicates)
    assert result.count == 1
    assert len(result.groups[0]) == 2


def test_no_duplicates(simple_graph: Graph) -> None:
    result = DuplicatesKpi().collect(simple_graph)
    assert result.count == 0


# ---------------------------------------------------------------------------
# RichSnippetsKpi
# ---------------------------------------------------------------------------


def test_rich_snippets_excludes_helper_only_google_types() -> None:
    recipe = _uri("recipe/1")
    quantity = _uri("quantity/1")
    g = _g(
        (recipe, RDF.type, _schema("Recipe")),
        (recipe, _schema("name"), Literal("Pasta")),
        (recipe, _schema("image"), Literal("https://example.org/pasta.jpg")),
        (quantity, RDF.type, _schema("QuantitativeValue")),
        (quantity, _schema("minValue"), Literal(1)),
        (quantity, _schema("maxValue"), Literal(3)),
        (quantity, _schema("unitCode"), Literal("DAY")),
        (quantity, _schema("value"), Literal(2)),
    )

    result = RichSnippetsKpi().collect(g)

    assert result.eligible_valid == {f"{_SCHEMA}Recipe": 1}
    assert result.eligible_invalid == {}


# ---------------------------------------------------------------------------
# SchemaComplianceKpi — subgraph assembly
# ---------------------------------------------------------------------------


def test_schema_compliance_child_inclusion(
    graph_with_children: Graph, tmp_path: Path
) -> None:
    """Children with IRI prefix of the root IRI are included in the subgraph."""
    from wordlift_sdk.graph.audit.kpis.schema_compliance import _build_subgraph

    normalized = graph_with_children
    all_subjects = {s for s in normalized.subjects() if isinstance(s, URIRef)}
    subgraph = _build_subgraph(
        normalized,
        "https://example.org/entity/1",
        depth=1,
        all_subjects=all_subjects,
    )
    subject_strs = {str(s) for s in subgraph.subjects()}
    assert "https://example.org/entity/1" in subject_strs
    assert "https://example.org/entity/1/part" in subject_strs


def test_schema_compliance_empty_graph() -> None:
    from wordlift_sdk.graph.audit.kpis.schema_compliance import SchemaComplianceKpi
    from wordlift_sdk.validation.shacl import resolve_shape_specs

    kpi = SchemaComplianceKpi(shape_specs=resolve_shape_specs(), depth=1)
    result = kpi.collect(Graph())
    assert result.by_url == []


# ---------------------------------------------------------------------------
# GraphAuditor integration
# ---------------------------------------------------------------------------


def test_auditor_returns_report(tmp_path: Path) -> None:
    ttl = tmp_path / "graph.ttl"
    ttl.write_text(
        textwrap.dedent(
            """\
            @prefix schema: <http://schema.org/> .
            <https://example.org/article/1>
                a schema:Article ;
                schema:url "https://example.org/article/1" ;
                schema:name "Test Article" .
            """
        )
    )
    report = GraphAuditor().audit(ttl, AuditOptions())
    assert report.totals.total_entities == 1
    assert report.unique_urls.count == 1
    d = report.to_dict()
    assert "total_entities" in d
    assert "schema_compliance" in d
    text = report.to_text()
    assert "Graph Audit Report" in text


# ---------------------------------------------------------------------------
# AuditOptions — shape selection and issue_level
# ---------------------------------------------------------------------------


def test_exclude_builtin_shapes_reduces_spec_count() -> None:
    from wordlift_sdk.graph.audit._profile import shape_specs_for_profile
    from wordlift_sdk.validation.shacl import resolve_shape_specs

    default = resolve_shape_specs()
    reduced = shape_specs_for_profile(
        None, exclude_builtin_shapes=["google-article.ttl"]
    )
    assert len(reduced) == len(default) - 1
    assert "google-article.ttl" not in reduced


def test_builtin_shapes_include_list() -> None:
    from wordlift_sdk.graph.audit._profile import shape_specs_for_profile

    specs = shape_specs_for_profile(None, builtin_shapes=["google-article.ttl"])
    assert specs == ["google-article.ttl"]


def test_extra_shapes_appended(tmp_path: Path) -> None:
    from wordlift_sdk.graph.audit._profile import shape_specs_for_profile

    fake_shape = tmp_path / "custom.ttl"
    fake_shape.write_text(
        "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        "@prefix schema: <http://schema.org/> .\n"
    )
    specs = shape_specs_for_profile(None, extra_shapes=[str(fake_shape)])
    assert str(fake_shape) in specs


def test_issue_level_error_suppresses_warnings() -> None:
    from wordlift_sdk.graph.audit.kpis.schema_compliance import _extract_issues

    from rdflib import Literal as RLiteral
    from rdflib.namespace import SH as SH_NS

    report_graph = Graph()
    w_node = URIRef("urn:w1")
    report_graph.add((w_node, SH_NS.resultSeverity, SH_NS.Warning))
    report_graph.add((w_node, SH_NS.resultMessage, RLiteral("just a warning")))

    errors, warnings = _extract_issues(report_graph, {}, issue_level="error")
    assert errors == []
    assert warnings == []  # suppressed by error-only level


def test_issue_level_warning_keeps_warnings() -> None:
    from wordlift_sdk.graph.audit.kpis.schema_compliance import _extract_issues

    from rdflib import Literal as RLiteral
    from rdflib.namespace import SH as SH_NS

    report_graph = Graph()
    w_node = URIRef("urn:w1")
    report_graph.add((w_node, SH_NS.resultSeverity, SH_NS.Warning))
    report_graph.add((w_node, SH_NS.resultMessage, RLiteral("just a warning")))

    errors, warnings = _extract_issues(report_graph, {}, issue_level="warning")
    assert errors == []


# ---------------------------------------------------------------------------
# build_subgraph (public API)
# ---------------------------------------------------------------------------


def test_build_subgraph_returns_root_triples() -> None:
    from wordlift_sdk.graph.audit import build_subgraph

    entity = URIRef("https://example.org/article/1")
    graph = _g(
        (entity, RDF.type, _schema("Article")),
        (entity, _schema("url"), Literal("https://example.org/article/1")),
    )
    all_subjects = {s for s in graph.subjects() if isinstance(s, URIRef)}
    sg = build_subgraph(graph, "https://example.org/article/1", all_subjects)
    assert len(sg) == 2


def test_build_subgraph_includes_iri_prefix_children() -> None:
    from wordlift_sdk.graph.audit import build_subgraph

    root = URIRef("https://example.org/article/1")
    child = URIRef("https://example.org/article/1/section")
    graph = _g(
        (root, RDF.type, _schema("Article")),
        (root, _schema("url"), Literal("https://example.org/article/1")),
        (child, RDF.type, _schema("WebPageElement")),
    )
    all_subjects = {s for s in graph.subjects() if isinstance(s, URIRef)}
    sg = build_subgraph(graph, "https://example.org/article/1", all_subjects)
    assert (child, RDF.type, _schema("WebPageElement")) in sg


# ---------------------------------------------------------------------------
# build_entity_matrix
# ---------------------------------------------------------------------------


def _write_ttl(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "graph.ttl"
    p.write_text(textwrap.dedent(content))
    return p


def test_build_entity_matrix_basic(tmp_path: Path) -> None:
    from wordlift_sdk.graph.audit import build_entity_matrix

    ttl = _write_ttl(
        tmp_path,
        """\
        @prefix schema: <http://schema.org/> .
        <https://example.org/a> a schema:Article ;
            schema:url <https://example.org/a> .
        <https://example.org/b> a schema:FAQPage ;
            schema:url <https://example.org/b> .
        """,
    )
    rows = build_entity_matrix(ttl)
    assert len(rows) == 2
    urls = [r["url"] for r in rows]
    assert urls == sorted(urls)
    article_row = next(r for r in rows if r["url"] == "https://example.org/a")
    assert article_row["Article"] == 1
    assert article_row.get("FAQPage", 0) == 0


def test_build_entity_matrix_exclude_types(tmp_path: Path) -> None:
    from wordlift_sdk.graph.audit import build_entity_matrix

    ttl = _write_ttl(
        tmp_path,
        """\
        @prefix schema: <http://schema.org/> .
        <https://example.org/a> a schema:Article ;
            schema:url <https://example.org/a> .
        <https://example.org/b> a schema:WebPage ;
            schema:url <https://example.org/b> .
        """,
    )
    rows = build_entity_matrix(ttl, exclude_types=["WebPage"])
    # WebPage row still appears but the WebPage column is absent
    for row in rows:
        assert "WebPage" not in row


def test_build_entity_matrix_cluster(tmp_path: Path) -> None:
    from wordlift_sdk.graph.audit import build_entity_matrix

    ttl = _write_ttl(
        tmp_path,
        """\
        @prefix schema: <http://schema.org/> .
        <https://example.org/blog/post-1> a schema:Article ;
            schema:url <https://example.org/blog/post-1> .
        <https://example.org/blog/post-2> a schema:Article ;
            schema:url <https://example.org/blog/post-2> .
        <https://example.org/blog/post-3> a schema:BlogPosting ;
            schema:url <https://example.org/blog/post-3> .
        """,
    )
    rows = build_entity_matrix(ttl, cluster=True)
    urls = {r["url"] for r in rows}
    # post-1 and post-2 share the Article signature → collapsed
    assert "https://example.org/blog/*" in urls
    # post-3 has a different signature → kept separate
    assert "https://example.org/blog/post-3" in urls
    wildcard = next(r for r in rows if r["url"] == "https://example.org/blog/*")
    assert wildcard["Article"] == 2


def test_build_entity_matrix_empty_graph(tmp_path: Path) -> None:
    from wordlift_sdk.graph.audit import build_entity_matrix

    ttl = _write_ttl(tmp_path, "@prefix schema: <http://schema.org/> .\n")
    rows = build_entity_matrix(ttl)
    assert rows == []


def test_build_entity_matrix_columns_sorted(tmp_path: Path) -> None:
    from wordlift_sdk.graph.audit import build_entity_matrix

    ttl = _write_ttl(
        tmp_path,
        """\
        @prefix schema: <http://schema.org/> .
        <https://example.org/p> a schema:Article, schema:Thing ;
            schema:url <https://example.org/p> .
        """,
    )
    rows = build_entity_matrix(ttl)
    assert len(rows) == 1
    cols = list(rows[0].keys())
    type_cols = cols[1:]  # skip "url"
    assert type_cols == sorted(type_cols)

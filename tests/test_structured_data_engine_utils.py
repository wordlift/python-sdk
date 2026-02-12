from __future__ import annotations


import pytest
from rdflib import BNode, Graph, Literal, RDF, URIRef

import wordlift_sdk.structured_data.engine as engine


def test_type_and_id_helpers_are_deterministic():
    assert engine.normalize_type("schema:Article") == "Article"
    assert engine.normalize_type("https://schema.org/Thing") == "Thing"
    assert engine.normalize_type("http://schema.org/Thing") == "Thing"

    assert engine._slugify(" Hello, World ", "x") == "hello-world"
    assert engine._slugify("***", "x") == "x"
    assert engine._dash_type("HowToStep") == "how-to-step"
    assert engine._pluralize("category") == "categories"
    assert engine._pluralize("box") == "boxes"
    assert engine._pluralize("item") == "items"
    assert len(engine._hash_url("https://example.org", length=8)) == 8

    base = engine.build_output_basename("https://example.org/path")
    assert base.startswith("example-org-path--")

    iri = engine.build_id_base(
        "https://data.example.org/", "WebPage", "My Page", "https://example.org/p", 1
    )
    assert iri.startswith("https://data.example.org/web-pages/my-page-")


def test_path_and_shape_helpers():
    graph = Graph()
    list_head = BNode()
    graph.add((list_head, RDF.first, URIRef("https://schema.org/name")))
    tail = BNode()
    graph.add((list_head, RDF.rest, tail))
    graph.add((tail, RDF.first, URIRef("https://schema.org/headline")))
    graph.add((tail, RDF.rest, RDF.nil))

    items = engine._rdf_list_items(graph, list_head)
    assert len(items) == 2
    assert engine._path_to_string(graph, list_head) == "name.headline"
    assert engine._path_to_string(graph, URIRef("https://schema.org/url")) == "url"

    assert engine._short_schema_name(URIRef("https://schema.org/Thing")) == "Thing"
    assert engine._short_schema_name(URIRef("http://schema.org/Thing")) == "Thing"
    assert engine._short_schema_name(Literal("x")) is None


def test_runtime_token_replacement_helpers(caplog: pytest.LogCaptureFixture):
    yarrml = """
mappings:
  page:
    sources:
      - ['old.xhtml', 'xpath']
    s: __ID__~iri
    po:
      - [schema:url, '__URL__']
"""
    replaced = engine._replace_runtime_tokens(
        yarrml,
        file_uri="/tmp/page.xhtml",
        response={
            "id": "https://example.org/id",
            "web_page": {"url": "https://example.org/url"},
        },
    )
    assert "__ID__" not in replaced
    assert "__URL__" not in replaced
    assert "/tmp/page.xhtml" in replaced

    with pytest.raises(RuntimeError, match="__ID__"):
        engine._replace_runtime_tokens(yarrml, file_uri="/tmp/page.xhtml", response={})

    unresolved = engine._replace_runtime_tokens(
        "mappings:\n  page:\n    s: __URL__~iri\n",
        file_uri="/tmp/page.xhtml",
        replace_url=True,
        strict_url_token=False,
    )
    assert "__URL__" in unresolved
    assert "no runtime URL" in caplog.text


def test_replace_source_variants_and_reusable_mapping():
    src = "- ['foo.xhtml', 'xpath']\n- [foo.xhtml~xpath, '/']"
    assert "__XHTML__" in engine._replace_sources_with_placeholder(src, "__XHTML__")
    out = engine._replace_sources_with_file(src, "/tmp/a.xhtml")
    assert "/tmp/a.xhtml" in out

    reusable = engine.make_reusable_yarrrml(
        "s: https://example.org/p~iri\n- ['a.xhtml', 'xpath']",
        "https://example.org/p",
    )
    assert "__URL__" in reusable


def test_string_xpath_normalizers_and_quoting():
    assert engine._strip_quotes("'x'") == "x"
    assert engine._strip_wrapped_list("['x']") == "x"
    assert engine._strip_all_quotes("\"'x'\"") == "x"

    assert engine._normalize_xpath_literal("{ /html/title }") == "$(/html/title)"
    assert engine._normalize_xpath_literal("$(xpath://h1)") == "$(//h1))"
    assert engine._looks_like_xpath("$(//h1)") is True
    assert engine._looks_like_xpath("literal") is False
    assert engine._simplify_xpath("$(normalize-space(//h1))") == "//h1"
    assert (
        engine._normalize_xpath_reference("//div[contains(@class, 'hero')]/text()")
        == '//div[@class=\\"hero\\"]'
    )
    assert engine._first_list_value("['abc']") == "abc"

    quoted = engine._quote_unquoted_xpath_attributes("//*[@class=hero and @id=main]")
    assert '@class="hero"' in quoted
    assert '@id="main"' in quoted


def test_materialization_error_normalization():
    parser = engine._normalize_materialization_error(
        ValueError("ParserError while parsing")
    )
    assert "Malformed YARRRML" in str(parser)

    xpath = engine._normalize_materialization_error(
        ValueError("Unsupported XPath function")
    )
    assert "Unsupported XPath/function" in str(xpath)

    generic = engine._normalize_materialization_error(ValueError("boom"))
    assert "Failed to materialize" in str(generic)


def test_jsonld_and_blank_node_helpers():
    flat = engine._flatten_jsonld({"@graph": [{"@id": "x"}]})
    assert flat == [{"@id": "x"}]

    graph = Graph()
    graph.add(
        (
            URIRef("https://example.org/s"),
            URIRef("https://example.org/p"),
            URIRef("https://example.org/o"),
        )
    )
    engine.ensure_no_blank_nodes(graph)

    bad = Graph()
    bad.add((BNode(), URIRef("https://example.org/p"), URIRef("https://example.org/o")))
    with pytest.raises(RuntimeError, match="Blank nodes are not allowed"):
        engine.ensure_no_blank_nodes(bad)

    payload = {
        "@graph": [
            {"@id": "https://example.org/a~iri", "@type": "Thing", "name": "A"},
            {"wrapper": {"@id": "https://example.org/b~iri", "@type": "Thing"}},
        ]
    }
    nodes = engine._collect_jsonld_nodes(payload)
    assert len(nodes) >= 2
    normalized = engine._normalize_iri_suffixes(payload)
    assert normalized["@graph"][0]["@id"].endswith("/a")


def test_xpath_eval_helpers_and_item_list_building():
    class _Node:
        def __init__(self, text):
            self._text = text

        def text_content(self):
            return self._text

    class _Doc:
        def xpath(self, path):
            if path == '//div[@class="hero"]':
                return []
            if "contains(@class" in path:
                return [_Node(" Title ")]
            return ["  Value  "]

    assert engine._xpath_first_text(_Doc(), '//div[@class="hero"]') == "Title"

    class _BadDoc:
        def xpath(self, path):
            raise RuntimeError("bad")

    assert engine._xpath_first_text(_BadDoc(), "//h1") is None

    class _ListDoc:
        def xpath(self, path):
            if path == "//li":
                return [_Node("A"), _Node("A"), _Node("B")]
            raise RuntimeError("x")

    items = engine._extract_list_items(_ListDoc(), ["//li", "//missing"])
    assert items == ["A", "B"]

    item_list = engine._build_item_list(["A", "B"])
    assert item_list["@type"] == "ItemList"
    assert item_list["itemListElement"][0]["position"] == 1


def test_text_extraction_helpers():
    node = {"name": " Name ", "url": {"@id": "https://example.org"}}
    assert engine._extract_name(node) == "Name"
    assert (
        engine._extract_name_any({"https://schema.org/headline": {"@value": "H"}})
        == "H"
    )
    assert engine._extract_url_any(node) == "https://example.org"
    assert engine._extract_text_value([{"@value": " X "}]) == "X"
    assert engine._extract_type({"@type": ["schema:Article"]}) == "Article"
    assert engine._is_item_list_value([{"@type": "ItemList"}]) is True
    assert engine._local_prop_name("https://schema.org/name") == "name"
    assert engine._local_prop_name("schema:name") == "name"

from __future__ import annotations

from pathlib import Path

from rdflib import Graph, RDF, RDFS, URIRef

import wordlift_sdk.validation.generator as generator
from wordlift_sdk.validation.generator import FeatureData


def test_html_parsing_helpers_cover_core_patterns():
    assert generator._strip_tags("<p>Hello &amp; World</p>") == "Hello & World"
    assert generator._unique(["a", "a", "b"]) == ["a", "b"]

    assert generator._extract_schema_types("https://schema.org/Article") == ["Article"]
    assert generator._extract_schema_types("<h2><code>Article Product</code></h2>") == [
        "Article",
        "Product",
    ]

    assert (
        generator._table_kind("<table><th>Required properties</th></table>")
        == "required"
    )
    assert (
        generator._table_kind("<table><th>Recommended properties</th></table>")
        == "recommended"
    )
    assert generator._table_kind("<table><th>Other</th></table>") is None

    table_html = (
        "<table><tr><td><code>name</code></td><td>required</td></tr>"
        "<tr><td><code>offers</code><code>review</code></td><td>one of the following</td></tr></table>"
    )
    props, groups = generator._extract_table_properties(table_html)
    assert "name" in props
    assert any("offers" in group and "review" in group for group in groups)

    list_html = "<ul><li><code>name</code></li><li><code>offers</code></li></ul>"
    assert generator._extract_list_properties(list_html) == ["name", "offers"]

    gallery = '<a href="/search/docs/appearance/structured-data/product"></a>'
    assert generator._feature_urls_from_gallery(gallery) == [
        "https://developers.google.com/search/docs/appearance/structured-data/product"
    ]


def test_parse_feature_extracts_types_and_one_of():
    html = """
<h2><code>Product</code></h2>
<p>One of the following properties is required</p>
<ul><li><code>offers</code></li><li><code>review</code></li></ul>
<table>
  <th>Required properties</th>
  <tr><td><code>name</code></td></tr>
</table>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")
    assert "Product" in feature.types
    assert "name" in feature.types["Product"]["required"]
    assert any("offers" in group for group in feature.one_of["Product"])


def test_property_and_schema_helpers():
    assert generator._prop_path("name") == "schema:name"
    assert (
        generator._prop_path("review.reviewRating")
        == "( schema:review schema:reviewRating )"
    )

    assert generator._datatype_shapes("Text")
    assert generator._datatype_shapes("URL")
    assert generator._datatype_shapes("Number")
    assert generator._datatype_shapes("Unknown") == []

    uri = URIRef("http://schema.org/Thing")
    assert generator._short_name(uri) == "Thing"

    graph = Graph()
    cls = URIRef("http://schema.org/Thing")
    prop = URIRef("http://schema.org/name")
    graph.add((cls, RDF.type, RDFS.Class))
    graph.add((prop, RDF.type, RDF.Property))
    graph.add((prop, generator.SCHEMA_VOCAB.domainIncludes, cls))
    graph.add(
        (prop, generator.SCHEMA_VOCAB.rangeIncludes, URIRef("http://schema.org/Text"))
    )

    classes = generator._collect_classes(graph)
    props = generator._collect_properties(graph)
    domain_ranges = generator._collect_domain_ranges(graph, prop)

    assert cls in classes
    assert prop in props
    assert domain_ranges and domain_ranges[0][0] == cls


class _Resp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


def test_generate_google_shacls_and_entrypoint(monkeypatch, tmp_path: Path):
    gallery_url = generator.SEARCH_GALLERY_URL
    feature_url = (
        "https://developers.google.com/search/docs/appearance/structured-data/product"
    )

    pages = {
        gallery_url: '<a href="/search/docs/appearance/structured-data/product"></a>',
        feature_url: """
            <h2><code>Product</code></h2>
            <table><th>Required properties</th><tr><td><code>name</code></td></tr></table>
        """,
    }

    monkeypatch.setattr(
        generator.requests, "get", lambda url, timeout=30: _Resp(pages[url])
    )
    monkeypatch.setattr(generator, "tqdm", lambda seq, **kwargs: seq)

    rc = generator.generate_google_shacls(tmp_path, overwrite=True, limit=0, only=None)
    assert rc == 0
    assert (tmp_path / "google-product.ttl").exists()

    rc_only = generator.google_main(
        [
            "--output-dir",
            str(tmp_path),
            "--overwrite",
            "--only",
            "product",
        ]
    )
    assert rc_only == 0


def test_generate_schema_shacls_and_schema_main(monkeypatch, tmp_path: Path):
    out = tmp_path / "schemaorg-grammar.ttl"

    monkeypatch.setattr(
        generator.requests,
        "get",
        lambda url, timeout=60: _Resp(
            '{"@context": {"@vocab": "http://schema.org/"}, "@graph": []}'
        ),
    )
    monkeypatch.setattr(generator, "tqdm", lambda seq, **kwargs: seq)

    cls = URIRef("http://schema.org/Thing")
    prop = URIRef("http://schema.org/name")
    monkeypatch.setattr(generator, "_collect_classes", lambda graph: [cls])
    monkeypatch.setattr(generator, "_collect_properties", lambda graph: [prop])
    monkeypatch.setattr(
        generator,
        "_collect_domain_ranges",
        lambda graph, p: [(cls, [URIRef("http://schema.org/Text")])],
    )

    rc = generator.generate_schema_shacls(out, overwrite=True)
    assert rc == 0
    content = out.read_text(encoding="utf-8")
    assert "sh:targetClass schema:Thing" in content
    assert "sh:path schema:name" in content

    rc_main = generator.schema_main(["--output-file", str(out), "--overwrite"])
    assert rc_main == 0


def test_write_feature_respects_overwrite(tmp_path: Path):
    feature = FeatureData(
        url="https://example.org",
        types={"Thing": {"required": {"name"}, "recommended": set()}},
    )
    output_path = tmp_path / "google-thing.ttl"
    assert generator._write_feature(feature, output_path, overwrite=True) is True
    assert generator._write_feature(feature, output_path, overwrite=False) is False

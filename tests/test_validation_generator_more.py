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
    assert generator._extract_schema_types("<h3>Quiz</h3>") == ["Quiz"]

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
    props, groups, option_groups = generator._extract_table_properties(table_html)
    assert "name" in props
    assert any("offers" in group and "review" in group for group in groups)
    assert option_groups == []

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


def test_parse_feature_expands_explicit_schema_type_list_paragraph():
    html = """
<h3><code>Article</code> objects</h3>
<p>Article objects must be based on one of the following schema.org types:
<a href="https://schema.org/Article">Article</a>,
<a href="https://schema.org/NewsArticle">NewsArticle</a>,
<a href="https://schema.org/BlogPosting">BlogPosting</a>.</p>
<table><th>Recommended properties</th><tr><td><code>headline</code></td></tr></table>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")

    assert "Article" in feature.types
    assert "NewsArticle" in feature.types
    assert "BlogPosting" in feature.types
    assert "headline" in feature.types["Article"]["recommended"]
    assert "headline" in feature.types["NewsArticle"]["recommended"]
    assert "headline" in feature.types["BlogPosting"]["recommended"]


def test_parse_feature_uses_primary_paragraph_type_for_table_context():
    html = """
<h2><code>ImageObject</code></h2>
<p>{"@context":"https://schema.org/","@type":"ImageObject","creator":{"@type":"Person"}}</p>
<table>
  <th>Required properties</th>
  <tr>
    <td><code>contentUrl</code></td>
    <td>
      Google also supports the <code>url</code> property if you don't include
      <code>contentUrl</code>.
    </td>
  </tr>
</table>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")

    assert "ImageObject" in feature.types
    assert "Person" not in feature.types
    assert {"contentUrl", "url"} in feature.one_of["ImageObject"]


def test_parse_feature_paragraph_context_supports_multiple_explicit_types():
    html = """
<h2><code>ProfilePage</code></h2>
<table>
  <th>Required properties</th>
  <tr><td><code>mainEntity</code></td></tr>
</table>
<p>The full definition of <a href="https://schema.org/Person">Person</a> and
<a href="https://schema.org/Organization">Organization</a> is available on schema.org.</p>
<table>
  <th>Required properties</th>
  <tr><td><code>name</code></td></tr>
</table>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")

    assert "ProfilePage" in feature.types
    assert "mainEntity" in feature.types["ProfilePage"]["required"]
    assert "Person" in feature.types
    assert "Organization" in feature.types
    assert "name" in feature.types["Person"]["required"]
    assert "name" in feature.types["Organization"]["required"]


def test_parse_feature_initial_multi_type_paragraph_uses_primary_type():
    html = """
<p>{"@type":"ImageObject"}
<code><a href="https://schema.org/ImageObject">ImageObject</a></code>
<code><a href="https://schema.org/Person">Person</a></code></p>
<table>
  <th>Required properties</th>
  <tr><td><code>contentUrl</code></td></tr>
</table>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")

    assert "ImageObject" in feature.types
    assert "Person" not in feature.types
    assert "contentUrl" in feature.types["ImageObject"]["required"]


def test_extract_table_properties_handles_option_branches_and_ignores_urls():
    table_html = """
<table>
  <th>Required properties (choose the option that best suits your use case)</th>
  <tr><td>Option A</td></tr>
  <tr><td><code>applicableCountry</code></td><td>Text</td></tr>
  <tr><td><code>returnPolicyCategory</code></td><td><ul><li><code>https://schema.org/MerchantReturnFiniteReturnWindow</code></li></ul></td></tr>
  <tr><td>Option B</td></tr>
  <tr><td><code>merchantReturnLink</code></td><td>URL</td></tr>
</table>
"""
    props, groups, option_groups = generator._extract_table_properties(table_html)

    assert props == []
    assert groups == []
    assert option_groups
    assert len(option_groups[0]) == 2
    assert {"applicableCountry", "returnPolicyCategory"} in option_groups[0]
    assert {"merchantReturnLink"} in option_groups[0]


def test_extract_table_properties_handles_supported_fallback_alternative():
    table_html = """
<table>
  <th>Required properties</th>
  <tr>
    <td><code>contentUrl</code></td>
    <td>
      <p>A URL to the actual image content.</p>
      <aside>
        Google also supports the <code>url</code> property if you don\u2019t include
        <code>contentUrl</code>.
      </aside>
    </td>
  </tr>
</table>
"""
    props, groups, option_groups = generator._extract_table_properties(table_html)

    assert props == []
    assert {"contentUrl", "url"} in groups
    assert option_groups == []


def test_extract_table_properties_ignores_enum_value_lists_for_one_of():
    table_html = """
<table>
  <th>Required properties</th>
  <tr>
    <td><code>educationRequirements.credentialCategory</code></td>
    <td>
      Use one of the following values:
      <ul>
        <li><code>high school</code></li>
        <li><code>associate degree</code></li>
      </ul>
    </td>
  </tr>
</table>
"""
    props, groups, option_groups = generator._extract_table_properties(table_html)

    assert "educationRequirements.credentialCategory" in props
    assert groups == []
    assert option_groups == []


def test_parse_feature_downgrades_conditional_required_sections():
    html = """
<h2><code>MerchantReturnPolicy</code></h2>
<p>The following properties are required when you need seasonal overrides.</p>
<table>
  <th>Required properties</th>
  <tr><td><code>returnPolicySeasonalOverride</code></td></tr>
</table>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")

    assert "MerchantReturnPolicy" in feature.types
    assert (
        "returnPolicySeasonalOverride"
        not in feature.types["MerchantReturnPolicy"]["required"]
    )
    assert (
        "returnPolicySeasonalOverride"
        in feature.types["MerchantReturnPolicy"]["recommended"]
    )


def test_parse_feature_ignores_one_of_value_paragraph_lists():
    html = """
<h2><code>JobPosting</code></h2>
<table><th>Recommended properties</th><tr><td><code>educationRequirements.credentialCategory</code></td></tr></table>
<p>Use one of the following values:</p>
<ul>
  <li><code>high school</code></li>
  <li><code>associate degree</code></li>
</ul>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")

    assert "JobPosting" in feature.types
    assert (
        "educationRequirements.credentialCategory"
        in feature.types["JobPosting"]["recommended"]
    )
    assert not feature.one_of.get("JobPosting")


def test_extract_property_tokens_ignores_jsonld_meta_keys():
    tokens = generator._extract_property_tokens("@context @type @id name")
    assert "context" not in tokens
    assert "type" not in tokens
    assert "id" not in tokens
    assert "name" in tokens


def test_extract_property_tokens_normalizes_class_prefixed_property_path():
    tokens = generator._extract_property_tokens("ListItem.position")
    assert tokens == ["position"]


def test_extract_table_properties_ignores_one_of_types_enum_lists():
    table_html = """
<table>
  <th>Required properties</th>
  <tr>
    <td><code>expectsAcceptanceOf.category</code></td>
    <td>
      Use one of the following types:
      <ul>
        <li><code>public school</code></li>
        <li><code>government library</code></li>
      </ul>
    </td>
  </tr>
</table>
"""
    props, groups, option_groups = generator._extract_table_properties(table_html)

    assert "expectsAcceptanceOf.category" in props
    assert groups == []
    assert option_groups == []


def test_extract_table_properties_ignores_enum_rows_without_schema_type_refs():
    table_html = """
<table>
  <th>Recommended properties</th>
  <tr>
    <td><code>amenityFeature.name</code></td>
    <td><code><a href="https://schema.org/Text">Text</a></code></td>
  </tr>
  <tr>
    <td><code>wifi</code></td>
    <td>Whether the property has wifi.</td>
  </tr>
</table>
"""
    props, groups, option_groups = generator._extract_table_properties(table_html)

    assert "amenityFeature.name" in props
    assert "wifi" not in props
    assert groups == []
    assert option_groups == []


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

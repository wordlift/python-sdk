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


def test_parse_feature_treats_recommended_one_of_as_recommended_props():
    html = """
<h2><code>DefinedRegion</code></h2>
<table>
  <th>Required properties</th>
  <tr><td><code>addressCountry</code></td></tr>
</table>
<table>
  <th>Recommended properties</th>
  <tr>
    <td>Choose either <code>addressRegion</code> or <code>postalCode</code></td>
    <td>Delivery area hint.</td>
  </tr>
</table>
"""
    feature = generator._parse_feature(html, "https://example.org/feature")

    assert "DefinedRegion" in feature.types
    assert "addressCountry" in feature.types["DefinedRegion"]["required"]
    assert "addressRegion" not in feature.types["DefinedRegion"]["recommended"]
    assert "postalCode" not in feature.types["DefinedRegion"]["recommended"]
    assert {"addressRegion", "postalCode"} in feature.one_of_recommended[
        "DefinedRegion"
    ]


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


def test_write_feature_emits_recommended_one_of_for_scoped_types(tmp_path: Path):
    feature = FeatureData(
        url="https://example.org",
        types={
            "Product": {"required": {"offers"}, "recommended": set()},
            "Offer": {"required": {"price"}, "recommended": set()},
        },
        one_of_recommended={
            "Offer": [{"priceCurrency", "priceSpecification.priceCurrency"}]
        },
    )
    output_path = tmp_path / "google-product.ttl"
    assert generator._write_feature(feature, output_path, overwrite=True) is True
    content = output_path.read_text(encoding="utf-8")
    assert ":google_OfferRecommendedOneOf1Shape" in content
    assert "choose either priceCurrency or priceSpecification.priceCurrency" in content


# ---------------------------------------------------------------------------
# GS1 generator tests
# ---------------------------------------------------------------------------

_GS1_MINIMAL_TTL = """\
@prefix gs1: <https://ref.gs1.org/voc/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

gs1:Product
    rdf:type owl:Class ;
    rdf:type rdfs:Class ;
    rdfs:label "Product"@en .

gs1:Organization
    rdf:type owl:Class ;
    rdf:type rdfs:Class ;
    rdfs:label "Organization"@en .

gs1:productName
    rdf:type rdf:Property ;
    rdf:type owl:DatatypeProperty ;
    rdfs:domain gs1:Product ;
    rdfs:range xsd:string .

gs1:description
    rdf:type rdf:Property ;
    rdf:type owl:DatatypeProperty ;
    rdfs:domain gs1:Product ;
    rdfs:range rdf:langString .

gs1:relatedOrganization
    rdf:type rdf:Property ;
    rdf:type owl:ObjectProperty ;
    rdfs:domain gs1:Product ;
    rdfs:range gs1:Organization .
"""

_GS1_UNION_DOMAIN_TTL = """\
@prefix gs1: <https://ref.gs1.org/voc/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

gs1:Product  rdf:type owl:Class ; rdf:type rdfs:Class .
gs1:Organization  rdf:type owl:Class ; rdf:type rdfs:Class .

gs1:address
    rdf:type rdf:Property ;
    rdf:type owl:ObjectProperty ;
    rdfs:domain [
        rdf:type owl:Class ;
        owl:unionOf ( gs1:Product gs1:Organization )
    ] ;
    rdfs:range gs1:Organization .
"""


def _build_gs1_graph(ttl: str) -> Graph:
    g = Graph()
    g.parse(data=ttl, format="turtle")
    return g


def test_gs1_short_name():
    uri = URIRef("https://ref.gs1.org/voc/Product")
    assert generator._gs1_short_name(uri) == "Product"

    uri_other = URIRef("http://example.org/Foo")
    assert generator._gs1_short_name(uri_other) == "Foo"


def test_collect_gs1_classes():
    g = _build_gs1_graph(_GS1_MINIMAL_TTL)
    classes = generator._collect_gs1_classes(g)
    uris = [str(c) for c in classes]
    assert "https://ref.gs1.org/voc/Product" in uris
    assert "https://ref.gs1.org/voc/Organization" in uris


def test_collect_gs1_properties():
    g = _build_gs1_graph(_GS1_MINIMAL_TTL)
    props = generator._collect_gs1_properties(g)
    uris = [str(p) for p in props]
    assert "https://ref.gs1.org/voc/productName" in uris
    assert "https://ref.gs1.org/voc/description" in uris
    assert "https://ref.gs1.org/voc/relatedOrganization" in uris


def test_collect_gs1_domain_ranges_datatype():
    g = _build_gs1_graph(_GS1_MINIMAL_TTL)
    prop = URIRef("https://ref.gs1.org/voc/productName")
    result = generator._collect_gs1_domain_ranges(g, prop)
    assert len(result) == 1
    domain, ranges = result[0]
    assert str(domain) == "https://ref.gs1.org/voc/Product"
    assert any("string" in str(r) for r in ranges)


def test_collect_gs1_domain_ranges_object():
    g = _build_gs1_graph(_GS1_MINIMAL_TTL)
    prop = URIRef("https://ref.gs1.org/voc/relatedOrganization")
    result = generator._collect_gs1_domain_ranges(g, prop)
    assert len(result) == 1
    domain, ranges = result[0]
    assert str(domain) == "https://ref.gs1.org/voc/Product"
    assert any(str(r) == "https://ref.gs1.org/voc/Organization" for r in ranges)


def test_collect_gs1_domain_ranges_union():
    g = _build_gs1_graph(_GS1_UNION_DOMAIN_TTL)
    prop = URIRef("https://ref.gs1.org/voc/address")
    result = generator._collect_gs1_domain_ranges(g, prop)
    domains = {str(d) for d, _ in result}
    assert "https://ref.gs1.org/voc/Product" in domains
    assert "https://ref.gs1.org/voc/Organization" in domains


def test_collect_gs1_domain_ranges_no_domain():
    g = Graph()
    prop = URIRef("https://ref.gs1.org/voc/orphan")
    assert generator._collect_gs1_domain_ranges(g, prop) == []


def test_generate_gs1_shacls_output(monkeypatch, tmp_path: Path):
    out = tmp_path / "gs1-grammar.ttl"

    monkeypatch.setattr(
        generator.requests,
        "get",
        lambda url, timeout=60: _Resp(_GS1_MINIMAL_TTL),
    )
    monkeypatch.setattr(generator, "tqdm", lambda seq, **kwargs: seq)

    rc = generator.generate_gs1_shacls(out, overwrite=True)
    assert rc == 0

    content = out.read_text(encoding="utf-8")
    assert "sh:targetClass gs1:Product" in content
    assert "sh:path gs1:productName" in content
    assert "sh:path gs1:description" in content
    assert "sh:path gs1:relatedOrganization" in content
    assert "sh:class gs1:Organization" in content
    assert "sh:severity sh:Warning" in content

    # Verify valid Turtle
    parsed = Graph()
    parsed.parse(data=content, format="turtle")
    assert len(parsed) > 0


def test_generate_gs1_shacls_no_overwrite(monkeypatch, tmp_path: Path):
    out = tmp_path / "gs1-grammar.ttl"
    out.write_text("existing", encoding="utf-8")

    rc = generator.generate_gs1_shacls(out, overwrite=False)
    assert rc == 1
    assert out.read_text(encoding="utf-8") == "existing"


def test_gs1_main_entrypoint(monkeypatch, tmp_path: Path):
    out = tmp_path / "gs1-grammar.ttl"

    monkeypatch.setattr(
        generator.requests,
        "get",
        lambda url, timeout=60: _Resp(_GS1_MINIMAL_TTL),
    )
    monkeypatch.setattr(generator, "tqdm", lambda seq, **kwargs: seq)

    rc = generator.gs1_main(["--output-file", str(out), "--overwrite"])
    assert rc == 0
    assert out.exists()

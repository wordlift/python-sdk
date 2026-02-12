from __future__ import annotations

from rdflib import BNode, Graph, Literal, RDF, URIRef

import wordlift_sdk.structured_data.engine as engine
from wordlift_sdk.validation.shacl import ValidationResult


def test_ensure_node_ids_assigns_deterministic_ids_with_parent_rules():
    data = {
        "@graph": [
            {
                "@id": "_:root",
                "@type": "schema:Article",
                "name": "Root",
                "hasPart": {"@id": "_:part", "@type": "schema:Thing", "name": "Part"},
                "mentions": {
                    "@id": "_:mention",
                    "@type": "schema:Thing",
                    "name": "Mention",
                },
            }
        ]
    }

    engine._ensure_node_ids(
        data, "https://data.example.org", "https://example.org/page"
    )

    root = data["@graph"][0]
    assert root["@id"].startswith("https://data.example.org/")
    # hasPart uses parent-based base URI.
    assert root["hasPart"]["@id"].startswith(root["@id"])
    # mentions is independent, so it should not be parent-scoped.
    assert root["mentions"]["@id"].startswith("https://data.example.org/")


def test_normalize_jsonld_embed_and_graph_modes():
    data = [
        {
            "@id": "_:b0",
            "@type": "schema:WebPage",
            "name": "Page",
            "author": {"@id": "_:b1"},
        },
        {
            "@id": "_:b1",
            "@type": "schema:Person",
            "name": "Alice",
        },
    ]

    embedded = engine.normalize_jsonld(
        data,
        dataset_uri="https://data.example.org",
        url="https://example.org/page",
        target_type="WebPage",
        embed_nodes=True,
    )
    assert embedded["@context"] == "https://schema.org"
    assert isinstance(embedded["author"], dict)
    assert embedded["author"].get("name") == "Alice"

    graph_mode = engine.normalize_jsonld(
        data,
        dataset_uri="https://data.example.org",
        url="https://example.org/page",
        target_type="WebPage",
        embed_nodes=False,
    )
    assert "@graph" in graph_mode
    assert len(graph_mode["@graph"]) >= 2


def test_normalize_jsonld_errors_when_no_nodes():
    try:
        engine.normalize_jsonld(
            data={},
            dataset_uri="https://data.example.org",
            url="https://example.org/page",
            target_type="WebPage",
        )
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "No JSON-LD nodes" in str(exc)


def test_blank_node_errors_and_rewrite_refs():
    errs = engine._blank_node_errors({"@graph": [{"@type": "Thing"}]})
    assert errs

    id_map = {"_:b1": "https://data.example.org/things/a"}
    node_map = {
        "https://data.example.org/things/a": {
            "@id": "https://data.example.org/things/a",
            "name": "A",
        }
    }

    out_ref = engine._rewrite_refs({"@id": "_:b1"}, id_map, node_map, embed_nodes=False)
    assert out_ref == {"@id": "https://data.example.org/things/a"}

    out_embed = engine._rewrite_refs(
        {"@id": "_:b1"}, id_map, node_map, embed_nodes=True
    )
    assert out_embed.get("name") == "A"


def test_mapping_property_and_allowed_helpers(monkeypatch):
    monkeypatch.setattr(
        engine,
        "_schema_property_set",
        lambda: {"name", "author", "reviewRating", "url"},
    )

    mappings = [
        {
            "__main__": True,
            "name": "main",
            "type": "Review",
            "props": [
                ("schema:name", "$(//h1)"),
                ("schema:author", "ex:author~iri"),
                ("schema:reviewRating", "literal"),
                ("schema:url", "https://example.org/page"),
                ("schema:unknown", "literal"),
            ],
        },
        {"name": "author", "type": "Person", "props": []},
    ]

    mapped = engine._main_mapping_props(mappings)
    assert "name" in mapped and "author" in mapped

    missing_req = engine._missing_required_props(["name", "headline"], mapped)
    missing_rec = engine._missing_recommended_props(["author", "image"], mapped)
    assert missing_req == ["headline"]
    assert missing_rec == ["image"]

    guides = {
        "Review": {"required": ["name"], "recommended": ["reviewRating"]},
        "Person": {"required": ["name"], "recommended": []},
    }
    allowed = engine._google_allowed_properties(guides)
    assert "reviewBody" in allowed["Review"]

    allowed_set = engine._mapping_allowed_property_set(guides)
    assert "name" in allowed_set

    violations = engine._mapping_violations(mappings, allowed_set, "Review")
    assert any("property not allowed" in v for v in violations)
    assert any("reviewRating must map to a Rating node" in v for v in violations)


def test_xpath_and_mapping_sanity_helpers():
    mappings = [
        {
            "name": "review",
            "type": "Review",
            "props": [
                ("schema:name", "$(//h1)"),
                ("schema:author", "$(//missing)"),
                ("schema:reviewRating", "ex:author~iri"),
            ],
        },
        {"name": "author", "type": "Organization", "props": []},
    ]

    xhtml = "<html><body><h1>Title</h1><p> </p></body></html>"
    evidence = engine._xpath_evidence_errors(mappings, xhtml)
    assert any("XPath returned no results" in e for e in evidence)

    warnings = engine._xpath_reusability_warnings(
        [
            {
                "name": "x",
                "type": "Thing",
                "props": [("schema:name", "//*[@id='block-123']")],
            }
        ]
    )
    assert warnings == []

    sanity = engine._mapping_type_sanity(
        mappings, {"reviewRating": ("Rating",), "author": ("Person",)}
    )
    assert any("author must map to" in e for e in sanity) or any(
        "reviewRating must map to" in e for e in sanity
    )


def test_validation_message_helpers():
    report_graph = Graph()
    data_graph = Graph()

    res = BNode()
    shape = URIRef("urn:shape")
    focus = URIRef("urn:focus")
    path = URIRef("https://schema.org/name")

    report_graph.add((res, RDF.type, engine._SH.ValidationResult))
    report_graph.add((res, engine._SH.resultSeverity, engine._SH.Warning))
    report_graph.add((res, engine._SH.resultMessage, Literal("warn")))
    report_graph.add((res, engine._SH.resultPath, path))
    report_graph.add((res, engine._SH.sourceShape, shape))
    report_graph.add((res, engine._SH.focusNode, focus))
    data_graph.add((focus, RDF.type, URIRef("https://schema.org/Review")))

    result = ValidationResult(
        conforms=False,
        report_text="x",
        report_graph=report_graph,
        data_graph=data_graph,
        shape_source_map={shape: "shape.ttl"},
        warning_count=1,
    )

    errors, warnings = engine._validation_messages(result)
    assert not errors
    assert warnings and "shape.ttl" in warnings[0]

    errors2, warnings2 = engine._validation_messages_for_types(result, {"Review"})
    assert not errors2
    assert warnings2

    assert engine._format_result_path(path) == "name"
    assert engine._format_result_path(None) == "unknown"

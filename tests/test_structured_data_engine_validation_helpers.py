from __future__ import annotations

import asyncio
import builtins
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

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


def test_build_clients_and_get_dataset_uri_paths(monkeypatch):
    class _FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        def close(self):
            return None

    monkeypatch.setattr(engine, "ApiClient", _FakeApiClient)
    monkeypatch.setattr(engine, "resolve_ssl_ca_cert", lambda _v: "/tmp/ca.pem")

    client = engine._build_client("k", "https://api.example.org", ssl_ca_cert="custom")
    assert client.configuration.host == "https://api.example.org"
    assert client.configuration.api_key["ApiKey"] == "k"
    assert client.configuration.ssl_ca_cert == "/tmp/ca.pem"
    client.close()

    agent_client = engine._build_agent_client("k2", ssl_ca_cert="custom")
    assert agent_client.configuration.host == "https://api.wordlift.io/agent"
    assert agent_client.configuration.api_key["ApiKey"] == "k2"
    assert agent_client.configuration.ssl_ca_cert == "/tmp/ca.pem"
    agent_client.close()

    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(engine, "_build_client", lambda *_a, **_k: _Ctx())

    class _AccountApi:
        def __init__(self, _api_client):
            pass

        async def get_me(self):
            return SimpleNamespace(dataset_uri="https://data.example.org")

    monkeypatch.setattr(engine.wordlift_client, "AccountApi", _AccountApi)
    assert (
        asyncio.run(engine.get_dataset_uri_async("k", "https://api.example.org"))
        == "https://data.example.org"
    )

    class _MissingAccountApi:
        def __init__(self, _api_client):
            pass

        async def get_me(self):
            return SimpleNamespace(dataset_uri=None)

    monkeypatch.setattr(engine.wordlift_client, "AccountApi", _MissingAccountApi)
    try:
        asyncio.run(engine.get_dataset_uri_async("k", "https://api.example.org"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Failed to resolve dataset_uri" in str(exc)


def test_shape_and_property_guide_helpers_with_mock_graphs(monkeypatch):
    monkeypatch.setattr(engine, "_GOOGLE_SHAPES_CACHE", None)
    monkeypatch.setattr(engine, "_SCHEMA_SHAPES_CACHE", None)
    monkeypatch.setattr(engine, "_SCHEMA_PROP_CACHE", None)
    monkeypatch.setattr(engine, "_SCHEMA_RANGE_CACHE", None)

    google = Graph()
    schema = Graph()
    review_http = URIRef("http://schema.org/Review")
    review_https = URIRef("https://schema.org/Review")
    rating_http = URIRef("http://schema.org/Rating")

    shape_g = URIRef("urn:google:shape")
    prop_required = BNode()
    prop_recommended = BNode()
    google.add((shape_g, engine._SH.targetClass, review_https))
    google.add((shape_g, engine._SH.property, prop_required))
    google.add((prop_required, engine._SH.path, URIRef("https://schema.org/name")))
    google.add((prop_required, engine._SH.minCount, Literal(1)))
    google.add((shape_g, engine._SH.property, prop_recommended))
    google.add((prop_recommended, engine._SH.path, URIRef("https://schema.org/author")))
    google.add((prop_recommended, engine._SH.minCount, Literal(1)))
    google.add((prop_recommended, engine._SH.severity, engine._SH.Warning))

    shape_s = URIRef("urn:schema:shape")
    schema_prop = BNode()
    schema_or = BNode()
    schema_or_item = BNode()
    schema.add((shape_s, engine._SH.targetClass, review_http))
    schema.add((shape_s, engine._SH.property, schema_prop))
    schema.add((schema_prop, engine._SH.path, URIRef("http://schema.org/reviewRating")))
    schema.add((schema_prop, engine._SH["or"], schema_or))
    schema.add((schema_or, RDF.first, schema_or_item))
    schema.add((schema_or, RDF.rest, RDF.nil))
    schema.add((schema_or_item, engine._SH["class"], rating_http))

    monkeypatch.setattr(engine, "_load_google_shapes", lambda: google)
    monkeypatch.setattr(engine, "_load_schema_shapes", lambda: schema)

    props = engine._schema_property_set()
    assert "reviewRating" in props

    ranges = engine._schema_property_ranges()
    assert ranges["Review"]["reviewRating"] == {"Rating"}

    guide = engine._property_guide_for_type("Review")
    assert guide["required"] == ["name"]
    assert guide["recommended"] == ["author"]

    related = engine._related_types_for_type("Review", guide, ranges)
    assert related == []

    guides = engine.property_guides_with_related("Review", max_depth=1)
    assert "Review" in guides


def test_extract_agent_helpers_and_prompt_sections():
    payload = {"a": ["", " hello ", {"x": "world"}]}
    out: list[str] = []
    engine._collect_strings(payload, out)
    assert any("hello" in s for s in out)

    text = engine._extract_agent_text({"response": {"content": "mappings:\n  a: b"}})
    assert text and "mappings:" in text

    parsed = engine._extract_agent_json('prefix {"score": 8, "notes": []} suffix')
    assert parsed and parsed["score"] == 8

    prompt = engine._agent_prompt(
        url="https://example.com",
        html="<html/>",
        target_type="Review",
        property_guides={
            "Review": {
                "required": ["name"],
                "recommended": [],
                "optional": [],
                "schema": ["name"],
            }
        },
        missing_required=["name"],
        missing_recommended=["author"],
        previous_yarrml="mappings: {}",
        validation_errors=["bad"],
        validation_report=["report"],
        xpath_warnings=["warn"],
        allow_properties={"Review": ["name"]},
        quality_feedback=["feedback"],
    )
    assert "Missing required properties" in prompt
    assert "Allowed properties (Google only)" in prompt
    assert "Quality feedback from the previous mapping" in prompt

    quality_prompt = engine._quality_prompt(
        url="https://example.com",
        xhtml="<html/>",
        jsonld={"@type": "Review"},
        property_guides={
            "Review": {"required": ["name"], "recommended": [], "optional": []}
        },
        target_type="Review",
    )
    assert "structured data quality" in quality_prompt
    assert "JSON-LD" in quality_prompt


def test_normalize_xpath_and_yarrrml_parsing_helpers(monkeypatch):
    assert engine._normalize_xpath_literal("{/html/body/h1}") == "$(/html/body/h1)"
    assert engine._normalize_xpath_literal("$(xpath)/html/body") == "$(/html/body)"
    assert engine._normalize_xpath_literal('$(" //h1 ")') == "$( //h1 )"
    assert (
        engine._normalize_xpath_literal("$(xpath)','//h1/text()") == "$('//h1/text())"
    )

    assert engine._looks_like_xpath("$(//h1)")
    assert engine._simplify_xpath("$(normalize-space(//h1))") == "//h1"
    assert (
        engine._normalize_xpath_reference("//a[contains(@class,'author')]/text()")
        == '//a[@class=\\"author\\"]'
    )
    assert engine._first_list_value("['//h1']") == "//h1"

    monkeypatch.setattr(
        engine, "_schema_property_set", lambda: {"name", "author", "url"}
    )
    raw = """
mappings:
  main:
    sources:
      - [ value: "//article" ]
      - ["//section"]
    s: schema:Review
    po:
      - [schema:name, "{//h1/text()}"]
      - p: schema:author
        o: "$(//a[@class=author]/text())"
  author:
    s: schema:Person
    po:
      - [schema:name, "$(//a/text())"]
"""
    normalized, mappings = engine._normalize_agent_yarrml(
        raw=raw,
        url="https://example.com",
        file_uri="/tmp/page.xhtml",
        target_type="Review",
    )
    assert "schema:url" in normalized
    assert "schema:author" in normalized
    assert len(mappings) == 2

    try:
        engine._normalize_agent_yarrml(
            raw="prefixes:\n  schema: 'https://schema.org/'",
            url="https://example.com",
            file_uri="/tmp/page.xhtml",
            target_type="Review",
        )
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "recognizable mappings" in str(exc)

    quoted = engine._quote_unquoted_xpath_attributes("//a[@id=foo and @class=bar]")
    assert '@id="foo"' in quoted and '@class="bar"' in quoted


def test_generate_from_agent_success_and_quality_feedback(monkeypatch):
    monkeypatch.setattr(
        engine,
        "property_guides_with_related",
        lambda *_a, **_k: {"Review": {"required": ["name"], "recommended": ["author"]}},
    )
    monkeypatch.setattr(
        engine, "_google_allowed_properties", lambda _g: {"Review": ["name", "author"]}
    )
    monkeypatch.setattr(
        engine, "_mapping_allowed_property_set", lambda _g: {"name", "author", "url"}
    )
    monkeypatch.setattr(
        engine, "shape_specs_for_types", lambda _t: ["schemaorg-grammar.ttl"]
    )
    monkeypatch.setattr(engine, "ask_agent_for_yarrml", lambda *_a, **_k: "raw")
    monkeypatch.setattr(
        engine,
        "_normalize_agent_yarrml",
        lambda *_a, **_k: (
            "mappings:\n",
            [
                {
                    "__main__": True,
                    "name": "main",
                    "type": "Review",
                    "props": [
                        ("schema:name", "$(//h1)"),
                        ("schema:author", "ex:author~iri"),
                    ],
                }
            ],
        ),
    )
    monkeypatch.setattr(
        engine,
        "_materialize_jsonld",
        lambda _p: {"@graph": [{"@type": "Review", "name": "Title"}]},
    )
    monkeypatch.setattr(engine, "_ensure_node_ids", lambda *_a, **_k: None)
    monkeypatch.setattr(
        engine,
        "postprocess_jsonld",
        lambda *_a, **_k: {
            "@context": "https://schema.org",
            "@type": "Review",
            "name": "Title",
        },
    )
    monkeypatch.setattr(
        engine,
        "validate_file",
        lambda *_a, **_k: SimpleNamespace(
            conforms=True, warning_count=0, report_text="ok"
        ),
    )
    monkeypatch.setattr(
        engine, "_validation_messages_for_types", lambda *_a, **_k: ([], [])
    )
    monkeypatch.setattr(
        engine, "_main_mapping_props", lambda *_a, **_k: {"name", "author", "url"}
    )
    monkeypatch.setattr(engine, "_missing_required_props", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_missing_recommended_props", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_mapping_violations", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_xpath_evidence_errors", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_xpath_reusability_warnings", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_mapping_type_sanity", lambda *_a, **_k: [])
    monkeypatch.setattr(
        engine,
        "ask_agent_for_quality",
        lambda *_a, **_k: {
            "score": 8,
            "missing_in_jsonld": ["description"],
            "suggested_xpath": {"description": "//meta[@name='description']/@content"},
            "notes": ["Looks good"],
        },
    )

    with tempfile.TemporaryDirectory() as tmp:
        yarrml, jsonld_out = engine.generate_from_agent(
            url="https://example.com",
            html="<html>raw</html>",
            xhtml="<html>x</html>",
            cleaned_xhtml="<html>clean</html>",
            api_key="k",
            dataset_uri="https://data.example.org",
            target_type="Review",
            workdir=Path(tmp),
            max_retries=0,
            quality_check=True,
        )
        assert "mappings:" in yarrml
        assert jsonld_out["@type"] == "Review"
        assert (Path(tmp) / "requirements.json").is_file()
        assert (
            json.loads((Path(tmp) / "mapping.validation.json").read_text())["conforms"]
            is True
        )


def test_generate_from_agent_materialization_failure_raises(monkeypatch):
    monkeypatch.setattr(
        engine,
        "property_guides_with_related",
        lambda *_a, **_k: {"Review": {"required": ["name"], "recommended": []}},
    )
    monkeypatch.setattr(
        engine, "_google_allowed_properties", lambda _g: {"Review": ["name"]}
    )
    monkeypatch.setattr(
        engine, "_mapping_allowed_property_set", lambda _g: {"name", "url"}
    )
    monkeypatch.setattr(
        engine, "shape_specs_for_types", lambda _t: ["schemaorg-grammar.ttl"]
    )
    monkeypatch.setattr(engine, "ask_agent_for_yarrml", lambda *_a, **_k: "raw")
    monkeypatch.setattr(
        engine,
        "_normalize_agent_yarrml",
        lambda *_a, **_k: (
            "mappings:\n",
            [
                {
                    "__main__": True,
                    "name": "main",
                    "type": "Review",
                    "props": [("schema:name", "$(//h1)")],
                }
            ],
        ),
    )
    monkeypatch.setattr(
        engine,
        "_materialize_jsonld",
        lambda _p: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with tempfile.TemporaryDirectory() as tmp:
        try:
            engine.generate_from_agent(
                url="https://example.com",
                html="<html>raw</html>",
                xhtml="<html>x</html>",
                cleaned_xhtml="<html>clean</html>",
                api_key="k",
                dataset_uri="https://data.example.org",
                target_type="Review",
                workdir=Path(tmp),
                max_retries=0,
                quality_check=False,
            )
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "Failed to produce JSON-LD" in str(exc)
        validation_payload = json.loads(
            (Path(tmp) / "mapping.validation.json").read_text()
        )
        assert validation_payload["conforms"] is False


def test_load_shape_graphs_from_resources_and_cache(monkeypatch):
    class _Entry:
        def __init__(self, name: str, text: str, is_file: bool = True):
            self.name = name
            self._text = text
            self._is_file = is_file

        def is_file(self) -> bool:
            return self._is_file

        def read_text(self, encoding="utf-8") -> str:
            del encoding
            return self._text

    class _Dir:
        def __init__(self, entries: list[_Entry]):
            self._entries = entries

        def iterdir(self):
            return iter(self._entries)

        def joinpath(self, name: str):
            for entry in self._entries:
                if entry.name == name:
                    return entry
            return _Entry(name, "", is_file=False)

    ttl = (
        "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        "@prefix schema: <https://schema.org/> .\n"
        "[] a sh:NodeShape ; sh:targetClass schema:Review .\n"
    )
    review_entry = _Entry("google-review-snippet.ttl", ttl)
    schema_entry = _Entry("schemaorg-grammar.ttl", ttl)
    dir_obj = _Dir([review_entry, schema_entry, _Entry("notes.txt", "x")])

    monkeypatch.setattr(engine, "_GOOGLE_SHAPES_CACHE", None)
    monkeypatch.setattr(engine, "_SCHEMA_SHAPES_CACHE", None)
    monkeypatch.setattr(engine.resources, "files", lambda _name: dir_obj)

    g1 = engine._load_google_shapes()
    g2 = engine._load_google_shapes()
    assert g1 is g2
    s1 = engine._load_schema_shapes()
    s2 = engine._load_schema_shapes()
    assert s1 is s2


def test_load_schema_shapes_raises_when_schema_file_missing(monkeypatch):
    class _Missing:
        def is_file(self) -> bool:
            return False

    class _Dir:
        def joinpath(self, _name: str):
            return _Missing()

    monkeypatch.setattr(engine, "_SCHEMA_SHAPES_CACHE", None)
    monkeypatch.setattr(engine.resources, "files", lambda _name: _Dir())
    try:
        engine._load_schema_shapes()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "schemaorg-grammar.ttl not found" in str(exc)


def test_agent_async_and_sync_wrappers(monkeypatch):
    class _Ctx:
        async def __aenter__(self):
            return "client"

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _AgentApi:
        def __init__(self, client):
            assert client == "client"

        async def ask_request_api_ask_post(self, ask_request):
            assert ask_request.message
            return {"answer": "mappings:\n  m: {}"}

    monkeypatch.setattr(engine, "_build_agent_client", lambda *_a, **_k: _Ctx())
    monkeypatch.setattr(engine, "AgentApi", _AgentApi)

    payload = asyncio.run(engine._ask_agent_async("prompt", "k"))
    assert isinstance(payload, dict)

    out = engine.ask_agent_for_yarrml(
        api_key="k",
        url="https://example.com",
        html="<html/>",
        target_type="Review",
    )
    assert "mappings:" in out


def test_agent_wrapper_debug_and_error_paths(monkeypatch):
    async def _ok_async(*_a, **_k):
        return SimpleNamespace(model_dump=lambda: {"message": "hello"})

    monkeypatch.setattr(
        engine,
        "_ask_agent_async",
        _ok_async,
    )
    monkeypatch.setattr(
        engine, "_extract_agent_text", lambda payload: payload.get("message")
    )
    with tempfile.TemporaryDirectory() as tmp:
        debug_path = Path(tmp) / "agent-debug.json"
        out = engine.ask_agent_for_yarrml(
            api_key="k",
            url="https://example.com",
            html="<html/>",
            target_type="Review",
            debug=True,
            debug_path=debug_path,
        )
        assert out == "hello"
        assert debug_path.is_file()

    async def _boom_async(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_ask_agent_async", _boom_async)
    try:
        engine.ask_agent_for_yarrml("k", "https://example.com", "<html/>", "Review")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Agent request failed" in str(exc)

    async def _no_text_async(*_a, **_k):
        return {"nope": "x"}

    monkeypatch.setattr(engine, "_ask_agent_async", _no_text_async)
    monkeypatch.setattr(engine, "_extract_agent_text", lambda _payload: None)
    try:
        engine.ask_agent_for_yarrml("k", "https://example.com", "<html/>", "Review")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "did not include YARRRML" in str(exc)

    async def _quality_async(*_a, **_k):
        return {"score": 7}

    monkeypatch.setattr(engine, "_ask_agent_async", _quality_async)
    monkeypatch.setattr(engine, "_extract_agent_json", lambda payload: payload)
    out_quality = engine.ask_agent_for_quality(
        "k", "https://example.com", "<html/>", {"@type": "Review"}, None, "Review"
    )
    assert out_quality == {"score": 7}

    async def _quality_fail_async(*_a, **_k):
        raise RuntimeError("fail")

    monkeypatch.setattr(engine, "_ask_agent_async", _quality_fail_async)
    try:
        engine.ask_agent_for_quality(
            "k", "https://example.com", "<html/>", {"@type": "Review"}, None, "Review"
        )
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Agent quality request failed" in str(exc)


def test_materialize_yarrrml_and_xpath_evidence_error_branches(monkeypatch):
    monkeypatch.setattr(
        engine, "_replace_runtime_tokens", lambda *_a, **_k: "mappings:\n"
    )
    monkeypatch.setattr(engine, "_materialize_graph", lambda _path: Graph())
    with tempfile.TemporaryDirectory() as tmp:
        graph = engine.materialize_yarrrml(
            "mappings:\n",
            xhtml_path=Path(tmp) / "page.xhtml",
            workdir=Path(tmp) / "out",
        )
        assert isinstance(graph, Graph)
        assert (Path(tmp) / "out" / "mapping.yarrrml").is_file()

    errors = engine._xpath_evidence_errors(
        [
            {
                "name": "m",
                "props": [
                    ("schema:name", "$(/html/body//*[contains(@class,))"),
                    ("schema:url", "https://example.com"),
                ],
            }
        ],
        "<html><body><h1>x</h1></body></html>",
    )
    assert any("invalid XPath" in e for e in errors)


def test_generate_from_agent_mapping_errors_branch(monkeypatch, caplog):
    monkeypatch.setattr(
        engine,
        "property_guides_with_related",
        lambda *_a, **_k: {"Review": {"required": ["name"], "recommended": []}},
    )
    monkeypatch.setattr(
        engine, "_google_allowed_properties", lambda _g: {"Review": ["name"]}
    )
    monkeypatch.setattr(
        engine, "_mapping_allowed_property_set", lambda _g: {"name", "url"}
    )
    monkeypatch.setattr(
        engine, "shape_specs_for_types", lambda _t: ["schemaorg-grammar.ttl"]
    )
    monkeypatch.setattr(engine, "ask_agent_for_yarrml", lambda *_a, **_k: "raw")
    monkeypatch.setattr(
        engine,
        "_normalize_agent_yarrml",
        lambda *_a, **_k: (
            "mappings:\n",
            [
                {
                    "__main__": True,
                    "name": "main",
                    "type": "Review",
                    "props": [("schema:name", "$(//h1)")],
                }
            ],
        ),
    )
    monkeypatch.setattr(
        engine,
        "_materialize_jsonld",
        lambda _p: {"@graph": [{"@type": "Review", "name": "Title"}]},
    )
    monkeypatch.setattr(engine, "_ensure_node_ids", lambda *_a, **_k: None)
    monkeypatch.setattr(
        engine,
        "postprocess_jsonld",
        lambda *_a, **_k: {"@type": "Review", "name": "Title"},
    )
    monkeypatch.setattr(
        engine,
        "validate_file",
        lambda *_a, **_k: SimpleNamespace(
            conforms=True, warning_count=0, report_text="ok"
        ),
    )
    monkeypatch.setattr(
        engine, "_validation_messages_for_types", lambda *_a, **_k: ([], [])
    )
    monkeypatch.setattr(engine, "_main_mapping_props", lambda *_a, **_k: {"name"})
    monkeypatch.setattr(engine, "_missing_required_props", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_missing_recommended_props", lambda *_a, **_k: [])
    monkeypatch.setattr(
        engine, "_mapping_violations", lambda *_a, **_k: ["bad mapping"]
    )
    monkeypatch.setattr(engine, "_xpath_evidence_errors", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_xpath_reusability_warnings", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_mapping_type_sanity", lambda *_a, **_k: [])

    caplog.set_level("WARNING")
    with tempfile.TemporaryDirectory() as tmp:
        _, jsonld_out = engine.generate_from_agent(
            url="https://example.com",
            html="<html>raw</html>",
            xhtml="<html>x</html>",
            cleaned_xhtml="<html>clean</html>",
            api_key="k",
            dataset_uri="https://data.example.org",
            target_type="Review",
            workdir=Path(tmp),
            max_retries=0,
            quality_check=False,
        )
        assert jsonld_out["@type"] == "Review"
        payload = json.loads((Path(tmp) / "mapping.validation.json").read_text())
        assert payload["conforms"] is False
        assert payload["errors"] == ["bad mapping"]
    assert any(
        "failed validation after retries" in rec.message for rec in caplog.records
    )


def test_additional_property_guide_and_extract_branches(monkeypatch):
    google = Graph()
    schema = Graph()
    target = URIRef("https://schema.org/Review")
    shape = URIRef("urn:shape")
    prop = BNode()
    google.add((shape, engine._SH.targetClass, target))
    google.add((shape, engine._SH.property, prop))
    google.add((prop, engine._SH.path, URIRef("https://schema.org/name")))
    google.add((prop, engine._SH.minCount, Literal("not-an-int")))
    monkeypatch.setattr(engine, "_load_google_shapes", lambda: google)
    monkeypatch.setattr(engine, "_load_schema_shapes", lambda: schema)
    guide = engine._property_guide_for_type("Review")
    assert guide["required"] == []

    related = engine._related_types_for_type(
        "Review",
        {"required": ["author"], "recommended": []},
        {"Review": {"author": {"Thing", "Person"}}},
    )
    assert related == ["Person"]

    monkeypatch.setattr(
        engine, "_schema_property_ranges", lambda: {"Review": {"author": {"Person"}}}
    )
    monkeypatch.setattr(
        engine,
        "_property_guide_for_type",
        lambda t: {"required": ["author"]} if t == "Review" else {"required": []},
    )
    guides = engine.property_guides_with_related("Review", max_depth=1)
    assert "Person" in guides

    assert (
        engine._extract_agent_text({"nested": [" ", {"v": "plain text"}]})
        == "plain text"
    )
    assert engine._extract_agent_json("prefix {invalid} suffix") is None


def test_normalize_agent_yarrrml_additional_parser_branches(monkeypatch):
    monkeypatch.setattr(
        engine, "_schema_property_set", lambda: {"name", "author", "headline", "url"}
    )
    raw = """
mappings:
  main:
    p:
      schema:name:
        value: "['//h1/text()']"
      schema:author:
        mapping: author
    sources:
      - [['html'], "//article"]
      - ["//section"]
    s:schema:headline: "$(//h2/text())"
    s: Review
    po:
      - [a, 'schema:Review']
      - [p: schema:name, o: "$(//h1/text())"]
      - [p: a, o: "schema:Thing"]
  author:
    s: schema:Person
    po:
      - [schema:name, "$(//a/text())"]
"""
    normalized, mappings = engine._normalize_agent_yarrml(
        raw=raw,
        url="https://example.com",
        file_uri="/tmp/page.xhtml",
        target_type="Review",
    )
    assert "ex:author~iri" in normalized
    assert any(m["name"] == "main" for m in mappings)


def test_materialize_graph_and_xpath_first_text_branches():
    class _Doc:
        def __init__(self):
            self.calls = 0

        def xpath(self, path):
            self.calls += 1
            if self.calls == 1:
                return []
            raise RuntimeError("bad relaxed")

    assert engine._xpath_first_text(_Doc(), "//h1[@id='a']") is None


def test_ensure_node_ids_listitem_suffix_and_xpath_error_import_parse(monkeypatch):
    data = {
        "@graph": [
            {
                "@type": "ItemList",
                "itemListElement": [
                    {"@type": "ListItem", "position": "1", "item": {"name": "A"}},
                    {"@type": "ListItem", "position": "1", "item": {"name": "B"}},
                ],
            }
        ]
    }
    engine._ensure_node_ids(
        data, "https://data.example.org", "https://example.org/page"
    )
    items = data["@graph"][0]["itemListElement"]
    assert items[0]["@id"] != items[1]["@id"]
    assert "item-1" in items[0]["@id"]

    real_import = builtins.__import__

    def _missing_lxml(name, *args, **kwargs):
        if name == "lxml":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _missing_lxml)
    assert engine._xpath_evidence_errors([], "<html/>") == []
    monkeypatch.setattr(builtins, "__import__", real_import)

    from lxml import html as lxml_html

    monkeypatch.setattr(
        lxml_html,
        "document_fromstring",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("bad html")),
    )
    assert engine._xpath_evidence_errors([], "<html/>") == []


def test_generate_from_agent_quality_runtime_error_is_ignored(monkeypatch):
    monkeypatch.setattr(
        engine,
        "property_guides_with_related",
        lambda *_a, **_k: {"Review": {"required": [], "recommended": []}},
    )
    monkeypatch.setattr(engine, "_google_allowed_properties", lambda _g: {"Review": []})
    monkeypatch.setattr(engine, "_mapping_allowed_property_set", lambda _g: {"url"})
    monkeypatch.setattr(
        engine, "shape_specs_for_types", lambda _t: ["schemaorg-grammar.ttl"]
    )
    monkeypatch.setattr(engine, "ask_agent_for_yarrml", lambda *_a, **_k: "raw")
    monkeypatch.setattr(
        engine,
        "_normalize_agent_yarrml",
        lambda *_a, **_k: (
            "mappings:\n",
            [{"__main__": True, "name": "main", "type": "Review", "props": []}],
        ),
    )
    monkeypatch.setattr(
        engine, "_materialize_jsonld", lambda _p: {"@graph": [{"@type": "Review"}]}
    )
    monkeypatch.setattr(engine, "_ensure_node_ids", lambda *_a, **_k: None)
    monkeypatch.setattr(
        engine, "postprocess_jsonld", lambda *_a, **_k: {"@type": "Review"}
    )
    monkeypatch.setattr(
        engine,
        "validate_file",
        lambda *_a, **_k: SimpleNamespace(
            conforms=True, warning_count=0, report_text="ok"
        ),
    )
    monkeypatch.setattr(
        engine, "_validation_messages_for_types", lambda *_a, **_k: ([], [])
    )
    monkeypatch.setattr(engine, "_main_mapping_props", lambda *_a, **_k: {"url"})
    monkeypatch.setattr(engine, "_missing_required_props", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_missing_recommended_props", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_mapping_violations", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_xpath_evidence_errors", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_xpath_reusability_warnings", lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "_mapping_type_sanity", lambda *_a, **_k: [])
    monkeypatch.setattr(
        engine,
        "ask_agent_for_quality",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("quality failed")),
    )

    with tempfile.TemporaryDirectory() as tmp:
        yarrml, jsonld_out = engine.generate_from_agent(
            url="https://example.com",
            html="<html>raw</html>",
            xhtml="<html>x</html>",
            cleaned_xhtml="<html>clean</html>",
            api_key="k",
            dataset_uri="https://data.example.org",
            target_type="Review",
            workdir=Path(tmp),
            max_retries=0,
            quality_check=True,
        )
        assert "mappings:" in yarrml
        assert jsonld_out["@type"] == "Review"

import json
from pathlib import Path

import pytest
from rdflib import Graph, URIRef

import wordlift_sdk.structured_data.validation as validation_module
from wordlift_sdk.structured_data.io import (
    default_output_paths,
    normalize_output_format,
    serialize_graph,
    write_output,
)
from wordlift_sdk.structured_data.schema_guide import SchemaGuide
from wordlift_sdk.structured_data.validation import ValidationService


def test_write_output_creates_parent_dirs(tmp_path: Path):
    out = tmp_path / "nested" / "file.txt"
    write_output(out, "hello")
    assert out.read_text() == "hello"


def test_default_output_paths(tmp_path: Path):
    jsonld, yarrml = default_output_paths(tmp_path, "page")
    assert jsonld.name == "page.jsonld"
    assert yarrml.name == "page.yarrml"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("ttl", ("turtle", "ttl")),
        ("jsonld", ("json-ld", "jsonld")),
        ("json-ld", ("json-ld", "jsonld")),
        ("rdf", ("xml", "rdf")),
        ("nt", ("nt", "nt")),
        ("nq", ("nquads", "nq")),
    ],
)
def test_normalize_output_format_supported(value, expected):
    assert normalize_output_format(value) == expected


def test_normalize_output_format_unsupported():
    with pytest.raises(RuntimeError, match="Unsupported format"):
        normalize_output_format("yaml")


def test_serialize_graph_handles_str_and_bytes(monkeypatch):
    graph = Graph()
    graph.add((URIRef("urn:s"), URIRef("urn:p"), URIRef("urn:o")))

    ttl = serialize_graph(graph, "ttl")
    assert "ns1:s" in ttl

    class _BytesGraph:
        def serialize(self, format):
            return b"bytes-output"

    assert serialize_graph(_BytesGraph(), "ttl") == "bytes-output"


def test_schema_guide_and_validation_service(monkeypatch, tmp_path: Path):
    guide = SchemaGuide()
    assert guide.shape_specs_for_type(None) == []

    class _Result:
        conforms = True
        warning_count = 0
        report_text = "ok"

    monkeypatch.setattr(
        validation_module, "validate_file", lambda path, shape_specs: _Result()
    )

    service = ValidationService(schema=guide)
    report = service.validate(tmp_path / "in.jsonld", "Article", tmp_path)

    assert report == "ok"
    payload = json.loads((tmp_path / "jsonld.validation.json").read_text())
    assert payload["conforms"] is True

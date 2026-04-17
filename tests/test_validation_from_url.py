from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from rdflib import Graph

import wordlift_sdk.validation.shacl as shacl_module


def _fake_render_html(html: str):
    def _render_html(_options):
        return SimpleNamespace(html=html)

    return _render_html


class _FakePreparedValidator:
    prepared_shapes = SimpleNamespace(shape_source_map={}, shapes_graph=Graph())

    def validate_graph(self, data_graph, *, normalize_schema_org=True):
        return SimpleNamespace(
            conforms=True,
            report_graph=Graph(),
            report_text="OK",
            data_graph=data_graph,
            warning_count=0,
        )


def test_validate_jsonld_from_url_extracts_and_flattens(monkeypatch):
    html = """
    <html><head>
    <script type="application/ld+json">{"@context":{"@vocab":"http://schema.org/"},"@type":"WebPage","@id":"https://example.com"}</script>
    <script type="application/ld+json">{"@context":{"@vocab":"http://schema.org/"},"@graph":[{"@type":"Organization","name":"Acme"},{"@type":"WebSite","name":"Example"}]}</script>
    </head><body></body></html>
    """
    monkeypatch.setattr(shacl_module, "render_html", _fake_render_html(html))
    monkeypatch.setattr(
        shacl_module.PreparedShaclValidator,
        "from_shape_specs",
        lambda *_args, **_kwargs: _FakePreparedValidator(),
    )

    result = shacl_module.validate_jsonld_from_url("https://example.com")

    assert result.conforms is True
    assert result.report_text == "OK"
    graph_json = result.data_graph.serialize(format="json-ld")
    payload = json.loads(graph_json)
    assert isinstance(payload, list)
    assert len(payload) == 3


def test_validate_jsonld_from_url_invalid_fragment(monkeypatch):
    html = (
        "<html><head>"
        '<script type="application/ld+json">{invalid json}</script>'
        "</head></html>"
    )
    monkeypatch.setattr(shacl_module, "render_html", _fake_render_html(html))

    with pytest.raises(RuntimeError, match=re.escape("Invalid JSON-LD fragment #1")):
        shacl_module.validate_jsonld_from_url("https://example.com")


def test_validate_jsonld_from_url_no_fragments(monkeypatch):
    html = "<html><head></head><body>No jsonld</body></html>"
    monkeypatch.setattr(shacl_module, "render_html", _fake_render_html(html))

    with pytest.raises(RuntimeError, match="No JSON-LD fragments found"):
        shacl_module.validate_jsonld_from_url("https://example.com")

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from wordlift_sdk.validation.shacl import validate_jsonld_from_url


def _fake_render_html(html: str):
    def _render_html(_options):
        return SimpleNamespace(html=html)

    return _render_html


def _fake_validate(*_args, **_kwargs):
    return True, SimpleNamespace(subjects=lambda *_args, **_kwargs: []), "OK"


def _fake_shapes(*_args, **_kwargs):
    return SimpleNamespace(), {}


def test_validate_jsonld_from_url_extracts_and_flattens(monkeypatch):
    html = """
    <html><head>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","@id":"https://example.com"}</script>
    <script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"Acme"},{"@type":"WebSite","name":"Example"}]}</script>
    </head><body></body></html>
    """
    monkeypatch.setattr(
        "wordlift_sdk.validation.shacl.render_html", _fake_render_html(html)
    )
    monkeypatch.setattr("wordlift_sdk.validation.shacl.validate", _fake_validate)
    monkeypatch.setattr(
        "wordlift_sdk.validation.shacl._load_shapes_graph", _fake_shapes
    )

    result = validate_jsonld_from_url("https://example.com")

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
    monkeypatch.setattr(
        "wordlift_sdk.validation.shacl.render_html", _fake_render_html(html)
    )

    with pytest.raises(RuntimeError, match=re.escape("Invalid JSON-LD fragment #1")):
        validate_jsonld_from_url("https://example.com")


def test_validate_jsonld_from_url_no_fragments(monkeypatch):
    html = "<html><head></head><body>No jsonld</body></html>"
    monkeypatch.setattr(
        "wordlift_sdk.validation.shacl.render_html", _fake_render_html(html)
    )

    with pytest.raises(RuntimeError, match="No JSON-LD fragments found"):
        validate_jsonld_from_url("https://example.com")

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from rdflib import Graph

import wordlift_sdk.kg_build.rml_mapping as rml_module
from wordlift_sdk.kg_build.rml_mapping import RmlMappingService


class _Pipeline:
    def normalize(self, content, url, data_path, response=None):
        del url, data_path, response
        return content, {"x": "y"}

    def materialize(self, normalized, data_path, out_dir, url=None, response=None):
        del normalized, data_path, out_dir, url, response
        return {
            "@context": "https://schema.org",
            "@id": "https://example.com/a",
            "@type": "Thing",
        }

    def postprocess(self, jsonld_raw, mappings, xhtml_str, dataset_uri, url):
        del mappings, xhtml_str, dataset_uri, url
        return jsonld_raw


def _context(dataset_uri: str | None):
    return SimpleNamespace(account=SimpleNamespace(dataset_uri=dataset_uri))


@pytest.mark.asyncio
async def test_apply_mapping_from_content_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RmlMappingService(_context("https://data.example.com"))
    service._html_converter.convert = MagicMock(return_value="<html></html>")
    monkeypatch.setattr(rml_module, "MaterializationPipeline", _Pipeline)
    debug_output: dict[str, str] = {}

    graph = await service.apply_mapping(
        html="<html></html>",
        url="https://example.com/page",
        mapping_file_path="demo.yarrrml",
        mapping_content="m: 1",
        debug_output=debug_output,
    )
    assert isinstance(graph, Graph)
    assert len(graph) > 0
    assert debug_output["xhtml"] == "<html></html>"


@pytest.mark.asyncio
async def test_apply_mapping_file_not_found_returns_none() -> None:
    service = RmlMappingService(_context("https://data.example.com"))
    out = await service.apply_mapping(
        html="<html></html>",
        url="https://example.com",
        mapping_file_path=Path("/no/such/file.yarrrml"),
    )
    assert out is None


@pytest.mark.asyncio
async def test_apply_mapping_missing_dataset_uri_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RmlMappingService(_context(None))
    monkeypatch.setattr(rml_module, "MaterializationPipeline", _Pipeline)
    out = await service.apply_mapping(
        html="<html></html>",
        url="https://example.com",
        mapping_file_path="x",
        mapping_content="m: 1",
    )
    assert out is None


def test_normalize_schema_uris() -> None:
    service = RmlMappingService(_context("https://data.example.com"))
    payload = {
        "@context": "x",
        "https://schema.org/name": "https://schema.org/Thing",
        "list": ["https://schema.org/Article"],
    }
    normalized = service._normalize_schema_uris(payload)
    assert "@context" not in normalized
    assert "http://schema.org/name" in normalized
    assert normalized["list"][0] == "http://schema.org/Article"

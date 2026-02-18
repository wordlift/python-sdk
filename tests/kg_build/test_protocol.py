from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from rdflib import Graph, Literal, RDF, URIRef
from wordlift_client import WebPage, WebPageScrapeResponse

from wordlift_sdk.kg_build.config.loader import ProfileDefinition, ProfileMappingRoute
from wordlift_sdk.kg_build.protocol import ProfileImportProtocol


def _make_profile() -> ProfileDefinition:
    return ProfileDefinition(
        name="test-profile",
        inherit=None,
        api_key=None,
        mapping_mode="xpath",
        strict_mapping=True,
        mapping="default.yarrrml",
        templates_dir="profiles/test-profile/templates",
        mappings_dir="profiles/test-profile/mappings",
        routes=(ProfileMappingRoute(pattern=".*", mapping="default.yarrrml"),),
        settings={},
    )


def _make_context() -> MagicMock:
    context = MagicMock()
    context.account = SimpleNamespace(dataset_uri="https://data.example.com/dataset")
    return context


def _make_graph(subject: str) -> Graph:
    graph = Graph()
    s = URIRef(subject)
    graph.add((s, RDF.type, URIRef("http://schema.org/WebPage")))
    graph.add((s, URIRef("http://schema.org/url"), Literal("https://example.com/page")))
    return graph


@pytest.mark.asyncio
async def test_profile_protocol_reconciles_to_existing_id_and_sets_source():
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_graph("https://example.com/mapped-web-page")
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    existing_id = "https://example.com/entity/web-page-1"

    await protocol.callback(response, existing_web_page_id=existing_id)

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    assert (
        URIRef(existing_id),
        URIRef("https://w3id.org/seovoc/source"),
        Literal("web-page-import"),
    ) in patched_graph
    assert (
        URIRef(existing_id),
        RDF.type,
        URIRef("http://schema.org/WebPage"),
    ) in patched_graph


@pytest.mark.asyncio
async def test_profile_protocol_sets_source_on_mapped_subject_when_existing_id_missing():
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    mapped_subject = "https://example.com/mapped-web-page"
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_graph(mapped_subject)
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )

    await protocol.callback(response)

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    assert (
        URIRef(mapped_subject),
        URIRef("https://w3id.org/seovoc/source"),
        Literal("web-page-import"),
    ) in patched_graph

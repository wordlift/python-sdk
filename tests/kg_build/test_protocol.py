from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from rdflib import BNode, Graph, Literal, RDF, URIRef
from wordlift_client import WebPage, WebPageScrapeResponse

from wordlift_sdk.kg_build.config.loader import ProfileDefinition, ProfileMappingRoute
import wordlift_sdk.kg_build.protocol as protocol_module
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


def _make_profile_with_settings(settings: dict[str, object]) -> ProfileDefinition:
    profile = _make_profile()
    return ProfileDefinition(
        name=profile.name,
        inherit=profile.inherit,
        api_key=profile.api_key,
        mapping_mode=profile.mapping_mode,
        strict_mapping=profile.strict_mapping,
        mapping=profile.mapping,
        templates_dir=profile.templates_dir,
        mappings_dir=profile.mappings_dir,
        routes=profile.routes,
        settings=settings,
    )


def _make_context() -> SimpleNamespace:
    return SimpleNamespace(
        account=SimpleNamespace(dataset_uri="https://data.example.com/dataset"),
        client_configuration=SimpleNamespace(api_key={}),
        configuration_provider=SimpleNamespace(
            get_value=lambda *_args, **_kwargs: None
        ),
    )


def _make_graph(subject: str) -> Graph:
    graph = Graph()
    s = URIRef(subject)
    graph.add((s, RDF.type, URIRef("http://schema.org/WebPage")))
    graph.add((s, URIRef("http://schema.org/url"), Literal("https://example.com/page")))
    return graph


def _make_multi_entity_graph() -> Graph:
    graph = Graph()
    web_page = URIRef("https://example.com/entities/web-page")
    article = URIRef("https://example.com/entities/article")
    product = URIRef("https://example.com/entities/product")
    review = URIRef("https://example.com/entities/review")

    graph.add((web_page, RDF.type, URIRef("http://schema.org/WebPage")))
    graph.add((article, RDF.type, URIRef("http://schema.org/Article")))
    graph.add((product, RDF.type, URIRef("http://schema.org/Product")))
    graph.add((review, RDF.type, URIRef("http://schema.org/Review")))
    graph.add((web_page, URIRef("http://schema.org/mainEntity"), article))
    graph.add((article, URIRef("http://schema.org/review"), review))
    graph.add((article, URIRef("http://schema.org/about"), product))
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


@pytest.mark.asyncio
async def test_profile_protocol_sets_source_on_all_uri_subjects_in_graph():
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
        return_value=_make_multi_entity_graph()
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )

    await protocol.callback(response)

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    for iri in (
        URIRef("https://example.com/entities/web-page"),
        URIRef("https://example.com/entities/article"),
        URIRef("https://example.com/entities/product"),
        URIRef("https://example.com/entities/review"),
    ):
        assert (
            iri,
            URIRef("https://w3id.org/seovoc/source"),
            Literal("web-page-import"),
        ) in patched_graph


@pytest.mark.asyncio
async def test_profile_protocol_sets_source_when_web_page_absent_but_uri_subjects_exist():
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

    graph = Graph()
    article = URIRef("https://example.com/entities/article-only")
    graph.add((article, RDF.type, URIRef("http://schema.org/Article")))
    graph.add((article, URIRef("http://schema.org/headline"), Literal("Title")))
    protocol.rml_service.apply_mapping = AsyncMock(return_value=graph)

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )

    await protocol.callback(response)

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    assert (
        article,
        URIRef("https://w3id.org/seovoc/source"),
        Literal("web-page-import"),
    ) in patched_graph


@pytest.mark.asyncio
async def test_profile_protocol_does_not_set_source_on_blank_nodes():
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

    graph = Graph()
    article = URIRef("https://example.com/entities/article")
    blank = BNode()
    graph.add((article, RDF.type, URIRef("http://schema.org/Article")))
    graph.add((blank, RDF.type, URIRef("http://schema.org/Thing")))
    graph.add((article, URIRef("http://schema.org/mentions"), blank))
    protocol.rml_service.apply_mapping = AsyncMock(return_value=graph)

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )

    await protocol.callback(response)

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    assert (
        article,
        URIRef("https://w3id.org/seovoc/source"),
        Literal("web-page-import"),
    ) in patched_graph
    assert (
        blank,
        URIRef("https://w3id.org/seovoc/source"),
        Literal("web-page-import"),
    ) not in patched_graph


def test_protocol_uses_profile_postprocessor_runtime_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_loader(*, root_dir, profile_name, runtime=None):
        del root_dir, profile_name
        captured["runtime"] = runtime
        return []

    monkeypatch.setattr(protocol_module, "load_postprocessors_for_profile", fake_loader)
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_settings({"POSTPROCESSOR_RUNTIME": "persistent"}),
        root_dir=Path.cwd(),
    )
    assert protocol._postprocessor_runtime == "persistent"
    assert captured["runtime"] == "persistent"


def test_build_pp_context_exposes_resolved_profile_and_account_key() -> None:
    profile = _make_profile_with_settings(
        {"api_url": "https://profile-api.example.com"}
    )
    profile = ProfileDefinition(
        name=profile.name,
        inherit=profile.inherit,
        api_key="profile-secret",
        mapping_mode=profile.mapping_mode,
        strict_mapping=profile.strict_mapping,
        mapping=profile.mapping,
        templates_dir=profile.templates_dir,
        mappings_dir=profile.mappings_dir,
        routes=profile.routes,
        settings=profile.settings,
    )
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=profile,
        root_dir=Path.cwd(),
    )
    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )

    context = protocol._build_pp_context(
        "https://example.com/page", response, existing_web_page_id=None
    )

    assert context.account_key == "profile-secret"
    assert context.profile["name"] == "test-profile"
    assert context.profile["settings"]["api_url"] == "https://profile-api.example.com"


def test_apply_postprocessors_fails_fast_when_account_key_missing() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )

    class _NeverRun:
        name = "never-run"
        called = False

        def run(self, graph, context):
            self.called = True
            return graph

    handler = _NeverRun()
    protocol._postprocessors = [handler]  # type: ignore[assignment]

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    graph = _make_graph("https://example.com/mapped-web-page")

    with pytest.raises(RuntimeError, match="Postprocessor runtime requires an API key"):
        protocol._apply_postprocessors(
            graph,
            "https://example.com/page",
            response,
            existing_web_page_id=None,
        )

    assert handler.called is False

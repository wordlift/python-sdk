import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from jinja2 import UndefinedError
from rdflib import BNode, Graph, Literal, RDF, URIRef
from wordlift_client import WebPage, WebPageScrapeResponse
from wordlift_sdk.validation.shacl import ValidationResult

from wordlift_sdk.kg_build.config.loader import ProfileDefinition, ProfileMappingRoute
import wordlift_sdk.kg_build.protocol as protocol_module
from wordlift_sdk.kg_build.protocol import (
    ProfileImportProtocol,
    _path_contains_part,
    _resolve_postprocessor_runtime,
)


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


def _make_profile_with_overrides(**kwargs) -> ProfileDefinition:
    base = _make_profile()
    data = dict(base.__dict__)
    data.update(kwargs)
    return ProfileDefinition(**data)


def _make_context() -> SimpleNamespace:
    return SimpleNamespace(
        account=SimpleNamespace(dataset_uri="https://data.example.com/dataset"),
        client_configuration=SimpleNamespace(api_key={}),
        configuration_provider=SimpleNamespace(
            get_value=lambda *_args, **_kwargs: None
        ),
    )


def _make_context_without_dataset() -> SimpleNamespace:
    return SimpleNamespace(
        account=SimpleNamespace(dataset_uri=None),
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


def _make_dataset_scoped_graph() -> Graph:
    graph = Graph()
    page = URIRef("https://data.example.com/dataset/web-pages/1")
    article = URIRef("https://data.example.com/dataset/entities/article-1")
    external = URIRef("https://external.example.com/entities/ignore-me")

    graph.add((page, RDF.type, URIRef("https://schema.org/WebPage")))
    graph.add((page, RDF.type, URIRef("https://schema.org/CreativeWork")))
    graph.add((page, URIRef("https://schema.org/name"), Literal("Page 1")))
    graph.add((page, URIRef("https://schema.org/mainEntity"), article))
    graph.add((article, RDF.type, URIRef("https://schema.org/Article")))
    graph.add((article, URIRef("https://schema.org/headline"), Literal("Hello")))
    graph.add((external, RDF.type, URIRef("https://schema.org/Thing")))
    graph.add((external, URIRef("https://schema.org/name"), Literal("External")))
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
async def test_profile_protocol_sets_source_only_on_first_level_uri_subjects():
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
    assert (
        URIRef("https://example.com/entities/web-page"),
        URIRef("https://w3id.org/seovoc/source"),
        Literal("web-page-import"),
    ) in patched_graph
    for child in (
        URIRef("https://example.com/entities/article"),
        URIRef("https://example.com/entities/product"),
        URIRef("https://example.com/entities/review"),
    ):
        assert (
            child,
            URIRef("https://w3id.org/seovoc/source"),
            Literal("web-page-import"),
        ) not in patched_graph


@pytest.mark.asyncio
async def test_callback_runs_canonical_ids_after_postprocessors() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol.patcher.patch_all = AsyncMock()

    root = URIRef(
        "https://data.example.com/dataset/articles/"
        "article-7554bd49a18cf19eba0ecce8991880cd599582f9fe7eea595c471334d72921ef"
    )
    mapped_graph = Graph()
    mapped_graph.add((root, RDF.type, URIRef("http://schema.org/Article")))
    mapped_graph.add(
        (
            root,
            URIRef("http://schema.org/url"),
            Literal("https://translated.com/developers"),
        )
    )
    protocol.rml_service.apply_mapping = AsyncMock(return_value=mapped_graph)

    def _inject_service_product_and_fragment_offer(
        graph: Graph, *_args, **_kwargs
    ) -> Graph:
        graph.add((root, RDF.type, URIRef("http://schema.org/Product")))
        graph.add((root, RDF.type, URIRef("http://schema.org/Service")))
        graph.add(
            (
                root,
                URIRef("http://schema.org/url"),
                Literal("https://translated.com/developers"),
            )
        )
        graph.add(
            (
                root,
                URIRef("http://schema.org/offers"),
                URIRef(f"{root}#aggregate-offer-usd"),
            )
        )
        return graph

    protocol._apply_postprocessors = MagicMock(
        side_effect=_inject_service_product_and_fragment_offer
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://translated.com/developers", html="<html></html>")
    )
    await protocol.callback(response)

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    product_subjects = list(
        patched_graph.subjects(RDF.type, URIRef("http://schema.org/Product"))
    )
    assert len(product_subjects) == 1
    product_subject = product_subjects[0]
    assert str(product_subject).startswith("https://data.example.com/dataset/products/")
    assert "/articles/" not in str(product_subject)

    offers = list(
        patched_graph.objects(product_subject, URIRef("http://schema.org/offers"))
    )
    assert len(offers) == 1
    assert str(offers[0]).startswith(f"{product_subject}/offers/offer-")
    assert "#aggregate-offer-" not in str(offers[0])


@pytest.mark.asyncio
async def test_profile_protocol_applies_existing_import_hash_to_all_uri_subjects() -> (
    None
):
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
    await protocol.callback(response, existing_import_hash="abc123")

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    for iri in (
        URIRef("https://example.com/entities/web-page"),
        URIRef("https://example.com/entities/article"),
        URIRef("https://example.com/entities/product"),
        URIRef("https://example.com/entities/review"),
    ):
        assert (
            iri,
            URIRef("https://w3id.org/seovoc/importHash"),
            Literal("abc123"),
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
async def test_profile_protocol_sets_source_by_dataset_id_depth() -> None:
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
    page = URIRef("https://data.example.com/dataset/web-pages/1")
    entity = URIRef("https://data.example.com/dataset/entities/article-1")
    child = URIRef("https://data.example.com/dataset/entities/article-1/faq/1")
    graph.add((page, RDF.type, URIRef("https://schema.org/WebPage")))
    graph.add((page, URIRef("https://schema.org/mainEntity"), entity))
    graph.add((entity, RDF.type, URIRef("https://schema.org/Article")))
    graph.add((entity, URIRef("https://schema.org/hasPart"), child))
    graph.add((child, RDF.type, URIRef("https://schema.org/Question")))
    protocol.rml_service.apply_mapping = AsyncMock(return_value=graph)

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    patched_graph = protocol.patcher.patch_all.call_args.args[0]
    for iri in (page, entity):
        assert (
            iri,
            URIRef("https://w3id.org/seovoc/source"),
            Literal("web-page-import"),
        ) in patched_graph
    assert (
        child,
        URIRef("https://w3id.org/seovoc/source"),
        Literal("web-page-import"),
    ) not in patched_graph


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


def test_protocol_helpers_runtime_and_path_part() -> None:
    assert _path_contains_part("profiles/_base/templates", "_base") is True
    assert _path_contains_part("profiles/demo/templates", "_base") is False
    assert _resolve_postprocessor_runtime({}) == "persistent"
    assert (
        _resolve_postprocessor_runtime({"POSTPROCESSOR_RUNTIME": "persistent"})
        == "persistent"
    )


@pytest.mark.asyncio
async def test_callback_returns_early_on_errors() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol.patcher.patch_all = AsyncMock()
    response = SimpleNamespace(
        web_page=SimpleNamespace(url="https://x", html="<html></html>"),
        errors=["boom"],
    )

    await protocol.callback(response)

    protocol.patcher.patch_all.assert_not_called()


@pytest.mark.asyncio
async def test_callback_returns_early_when_html_missing() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol.patcher.patch_all = AsyncMock()
    response = WebPageScrapeResponse(web_page=WebPage(url="https://x", html=None))

    await protocol.callback(response)

    protocol.patcher.patch_all.assert_not_called()


@pytest.mark.asyncio
async def test_callback_returns_early_when_mapping_has_no_triples() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol.rml_service.apply_mapping = AsyncMock(return_value=Graph())
    protocol.patcher.patch_all = AsyncMock()

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    protocol.patcher.patch_all.assert_not_called()


def test_close_invokes_postprocessor_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def fake_close(postprocessors):
        called["value"] = postprocessors

    monkeypatch.setattr(protocol_module, "close_loaded_postprocessors", fake_close)
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol._postprocessors = ["x"]  # type: ignore[assignment]
    protocol.close()
    assert called["value"] == ["x"]


def test_resolve_path_and_overlay_paths(tmp_path: Path) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
    )
    absolute = Path("/tmp/abs-demo")
    assert protocol._resolve_path(str(absolute)) == absolute
    overlay = protocol._resolve_overlay_paths(("a", "b"))
    assert overlay == (tmp_path / "a", tmp_path / "b")


def test_resolve_mapping_path_prefers_existing_file(tmp_path: Path) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
    )
    mapping_name = "default.yarrrml"
    protocol.profile = ProfileDefinition(
        **{
            **protocol.profile.__dict__,
            "routes": (ProfileMappingRoute(pattern=".*", mapping=mapping_name),),
        }
    )
    d1 = tmp_path / "m1"
    d2 = tmp_path / "m2"
    d1.mkdir()
    d2.mkdir()
    (d2 / mapping_name).write_text("x", encoding="utf-8")
    protocol._mapping_dirs = (d1, d2)
    assert protocol._resolve_mapping_path("https://example.com") == d2 / mapping_name


def test_resolve_mapping_path_falls_back_to_last_dir(tmp_path: Path) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
    )
    d1 = tmp_path / "m1"
    d2 = tmp_path / "m2"
    d1.mkdir()
    d2.mkdir()
    protocol._mapping_dirs = (d1, d2)
    protocol.text_renderer.resolve_mapping_template = MagicMock(side_effect=lambda p: p)
    resolved = protocol._resolve_mapping_path("https://example.com")
    assert resolved == d2 / "default.yarrrml"


@pytest.mark.asyncio
async def test_patch_static_templates_once_records_and_writes_debug(
    tmp_path: Path,
) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
        debug_dir=tmp_path / "debug",
    )
    graph = Graph()
    s = URIRef("https://data.example.com/dataset/entities/x")
    graph.add((s, RDF.type, URIRef("https://schema.org/Thing")))
    protocol._template_graph = graph
    protocol._template_exports = {}
    protocol.patcher.patch_all = AsyncMock()

    await protocol._patch_static_templates_once()
    await protocol._patch_static_templates_once()

    protocol.patcher.patch_all.assert_called_once()
    assert (tmp_path / "debug" / "static_templates.ttl").exists()


@pytest.mark.asyncio
async def test_patch_static_templates_once_is_concurrency_safe() -> None:
    events: list[dict[str, object]] = []
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
        on_progress=lambda payload: events.append(payload),
    )
    graph = Graph()
    graph.add(
        (
            URIRef("https://data.example.com/dataset/entities/static"),
            RDF.type,
            URIRef("https://schema.org/Thing"),
        )
    )
    protocol._template_graph = graph
    protocol._template_exports = {}

    async def _patch_once(_: Graph, **_kwargs) -> None:
        await asyncio.sleep(0.01)

    protocol.patcher.patch_all = AsyncMock(side_effect=_patch_once)

    await asyncio.gather(
        *(protocol._patch_static_templates_once() for _ in range(8)),
    )

    protocol.patcher.patch_all.assert_called_once()
    static_events = [
        event for event in events if event.get("kind") == "static_templates"
    ]
    assert len(static_events) == 1
    assert protocol._static_templates_patched is True


def test_ensure_templates_loaded_requires_dataset_uri() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context_without_dataset(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    with pytest.raises(RuntimeError, match="Dataset URI not available"):
        protocol._ensure_templates_loaded()


def test_ensure_templates_loaded_handles_empty_templates() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol.text_renderer.load_exports_with_summary = MagicMock(
        return_value=(
            {"k": "v"},
            {
                "loaded_files": [],
                "source_keys": [],
                "effective_keys": [],
                "overrides": [],
                "searched_paths": [],
            },
        )
    )
    protocol.template_reifier.resolve_template_paths = MagicMock(
        return_value=([], {"source_files": [], "effective_files": [], "overrides": []})
    )
    protocol._ensure_templates_loaded()
    assert isinstance(protocol._template_graph, Graph)
    assert protocol._template_exports == {"k": "v"}


def test_ensure_templates_loaded_raises_runtime_for_missing_context() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol.text_renderer.load_exports_with_summary = MagicMock(
        return_value=(
            {},
            {
                "loaded_files": ["profiles/_base/exports.toml"],
                "source_keys": [],
                "effective_keys": [],
                "overrides": [],
                "searched_paths": ["profiles/_base/exports.toml"],
            },
        )
    )
    protocol.template_reifier.resolve_template_paths = MagicMock(
        return_value=(
            ["x"],
            {"source_files": [], "effective_files": [], "overrides": []},
        )
    )
    protocol.template_reifier.reify = MagicMock(
        side_effect=UndefinedError("missing value")
    )

    with pytest.raises(RuntimeError, match="Template rendering failed"):
        protocol._ensure_templates_loaded()


def test_get_mapping_content_uses_cache_and_requires_dataset() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    path = Path("m.yarrrml")
    protocol._mapping_cache[path] = "cached"
    assert protocol._get_mapping_content(path) == "cached"

    protocol2 = ProfileImportProtocol(
        context=_make_context_without_dataset(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    with pytest.raises(RuntimeError, match="Dataset URI not available"):
        protocol2._get_mapping_content(path)


def test_apply_postprocessors_runs_all_processors() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_settings({"api_key": "x"}),
        root_dir=Path.cwd(),
    )
    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    graph = _make_graph("https://example.com/page")

    class _P1:
        name = "p1"

        def run(self, g, _ctx):
            g.add(
                (
                    URIRef("https://example.com/page"),
                    URIRef("https://schema.org/name"),
                    Literal("a"),
                )
            )
            return g

    class _P2:
        name = "p2"

        def run(self, g, _ctx):
            return g

    protocol._postprocessors = [_P1(), _P2()]  # type: ignore[assignment]
    protocol._resolve_postprocessor_account_key = MagicMock(return_value="secret")
    out = protocol._apply_postprocessors(
        graph, "https://example.com/page", response, None
    )
    assert len(out) >= len(graph)


def test_resolve_postprocessor_account_key_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    protocol.profile = ProfileDefinition(
        **{**protocol.profile.__dict__, "api_key": "profile-key"}
    )
    assert protocol._resolve_postprocessor_account_key() == "profile-key"

    protocol.profile = ProfileDefinition(
        **{**protocol.profile.__dict__, "api_key": None}
    )
    protocol.context.client_configuration.api_key = {"ApiKey": "runtime-key"}
    assert protocol._resolve_postprocessor_account_key() == "runtime-key"

    protocol.context.client_configuration.api_key = {}
    protocol.context.configuration_provider = SimpleNamespace(
        get_value=lambda name: "provider-key" if name == "WORDLIFT_KEY" else None
    )
    assert protocol._resolve_postprocessor_account_key() == "provider-key"

    protocol.context.configuration_provider = SimpleNamespace(
        get_value=lambda _name: (_ for _ in ()).throw(RuntimeError("nope"))
    )
    monkeypatch.setenv("WORDLIFT_API_KEY", "env-key")
    assert protocol._resolve_postprocessor_account_key() == "env-key"
    monkeypatch.delenv("WORDLIFT_API_KEY", raising=False)


def test_clean_key_write_debug_and_reconcile(tmp_path: Path) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
        debug_dir=tmp_path / "debug",
    )
    assert protocol._clean_key(None) is None
    assert protocol._clean_key("  ") is None
    assert protocol._clean_key(" x ") == "x"

    graph = _make_graph("https://example.com/old")
    protocol._write_debug_graph(graph, "https://example.com/page")
    protocol._write_debug_source_documents(
        "https://example.com/page", "<html><body>Hi</body></html>", "<html/>"
    )
    assert any((tmp_path / "debug").iterdir())

    https_graph = Graph()
    old = URIRef("https://example.com/old")
    new = URIRef("https://example.com/new")
    child = URIRef("https://example.com/child")
    https_graph.add((old, RDF.type, URIRef("https://schema.org/WebPage")))
    https_graph.add((child, URIRef("https://schema.org/about"), old))
    assert protocol._find_web_page_iri(https_graph) == old
    protocol._reconcile_root_id(https_graph, str(new))
    assert (new, RDF.type, URIRef("https://schema.org/WebPage")) in https_graph
    assert (child, URIRef("https://schema.org/about"), new) in https_graph


@pytest.mark.asyncio
async def test_callback_writes_html_xhtml_and_ttl_debug_artifacts(
    tmp_path: Path,
) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
        debug_dir=tmp_path / "debug",
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()

    async def _apply_mapping(**kwargs):
        debug_output = kwargs.get("debug_output")
        if isinstance(debug_output, dict):
            debug_output["xhtml"] = "<html><body>Converted</body></html>"
        return _make_graph("https://example.com/mapped-web-page")

    protocol.rml_service.apply_mapping = AsyncMock(side_effect=_apply_mapping)

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html>Raw</html>")
    )

    await protocol.callback(response)

    safe_name = protocol_module.hashlib.sha256(
        "https://example.com/page".encode("utf-8")
    ).hexdigest()
    debug_dir = tmp_path / "debug"
    assert (debug_dir / f"{safe_name}.ttl").exists()
    assert (debug_dir / f"{safe_name}.html").exists()
    assert (debug_dir / f"{safe_name}.xhtml").exists()


def test_mapping_response_with_existing_id() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    mapped = protocol._mapping_response(response, "https://example.com/id")
    assert mapped.id == "https://example.com/id"
    assert mapped.web_page.url == "https://example.com/page"


def test_protocol_setting_parsers_and_progress_error_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    profile = _make_profile_with_overrides(
        settings={
            "SHACL_VALIDATE_MODE": "warn",
            "SHACL_BUILTIN_SHAPES": "google-article",
            "SHACL_EXCLUDE_BUILTIN_SHAPES": "schemaorg-grammar",
            "SHACL_EXTRA_SHAPES": "https://example.com/custom-shape.ttl",
            "IMPORT_HASH_MODE": "write",
        }
    )
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=profile,
        root_dir=Path.cwd(),
    )
    assert protocol._shacl_mode == "warn"
    assert protocol._shacl_shape_specs == [
        "google-article.ttl",
        "https://example.com/custom-shape.ttl",
    ]
    assert protocol._import_hash_mode == "write"
    assert protocol._resolve_list_setting(["a", " ", "b"]) == ["a", "b"]
    assert protocol._resolve_list_setting(123) == ["123"]

    protocol._on_progress = lambda _payload: (_ for _ in ()).throw(RuntimeError("boom"))
    with caplog.at_level("WARNING"):
        protocol._emit_progress({"kind": "graph"})
    assert "Failed to emit kg_build progress payload." in caplog.text


def test_resolve_mapping_path_absolute_and_templated(tmp_path: Path) -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
    )
    absolute = Path("/tmp/absolute.yarrrml")
    protocol.profile = _make_profile_with_overrides(
        routes=(ProfileMappingRoute(pattern=".*", mapping=str(absolute)),)
    )
    assert protocol._resolve_mapping_path("https://example.com") == absolute

    mapping_name = "templated.yarrrml"
    protocol.profile = _make_profile_with_overrides(
        routes=(ProfileMappingRoute(pattern=".*", mapping=mapping_name),)
    )
    d1 = tmp_path / "m1"
    d2 = tmp_path / "m2"
    d1.mkdir()
    d2.mkdir()
    templated = d2 / "templated.generated.yarrrml"

    def _resolve_template(candidate: Path) -> Path:
        if candidate == d2 / mapping_name:
            return templated
        return candidate

    protocol._mapping_dirs = (d1, d2)
    protocol.text_renderer.resolve_mapping_template = MagicMock(
        side_effect=_resolve_template
    )
    templated.write_text("x", encoding="utf-8")
    assert protocol._resolve_mapping_path("https://example.com") == templated


@pytest.mark.asyncio
async def test_patch_static_templates_fail_validation_raises() -> None:
    events: list[dict[str, object]] = []
    profile = _make_profile_with_overrides(
        settings={
            "shacl_validate_mode": "fail",
        }
    )
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=profile,
        root_dir=Path.cwd(),
        on_progress=lambda payload: events.append(payload),
    )
    graph = Graph()
    graph.add(
        (
            URIRef("https://data.example.com/dataset/entities/x"),
            RDF.type,
            URIRef("https://schema.org/Thing"),
        )
    )
    protocol._template_graph = graph
    protocol._template_exports = {}
    protocol.patcher.patch_all = AsyncMock()
    protocol._validate_graph = MagicMock(
        return_value=_make_validation_result(conforms=False)
    )

    with pytest.raises(
        RuntimeError, match="SHACL validation failed for static templates"
    ):
        await protocol._patch_static_templates_once()
    assert len(events) == 1
    assert events[0]["kind"] == "static_templates"
    assert events[0]["validation"] is not None
    assert events[0]["validation"]["pass"] is False
    protocol.patcher.patch_all.assert_not_called()


def test_find_web_page_iri_returns_none_when_missing() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    graph = Graph()
    graph.add(
        (
            URIRef("https://example.com/entities/x"),
            RDF.type,
            URIRef("https://schema.org/Thing"),
        )
    )
    assert protocol._find_web_page_iri(graph) is None


def _make_validation_result(
    *,
    conforms: bool,
    warning_shapes: list[URIRef] | None = None,
    error_shapes: list[URIRef] | None = None,
    shape_map: dict[URIRef, str] | None = None,
) -> ValidationResult:
    warning_shapes = warning_shapes or []
    error_shapes = error_shapes or []
    shape_map = shape_map or {}
    report = Graph()
    sh_result_severity = URIRef("http://www.w3.org/ns/shacl#resultSeverity")
    sh_warning = URIRef("http://www.w3.org/ns/shacl#Warning")
    sh_violation = URIRef("http://www.w3.org/ns/shacl#Violation")
    sh_source_shape = URIRef("http://www.w3.org/ns/shacl#sourceShape")

    for index, shape in enumerate(warning_shapes):
        node = URIRef(f"https://example.com/report/w/{index}")
        report.add((node, sh_result_severity, sh_warning))
        report.add((node, sh_source_shape, shape))
    for index, shape in enumerate(error_shapes):
        node = URIRef(f"https://example.com/report/e/{index}")
        report.add((node, sh_result_severity, sh_violation))
        report.add((node, sh_source_shape, shape))

    return ValidationResult(
        conforms=conforms,
        report_text="report",
        report_graph=report,
        data_graph=Graph(),
        shape_source_map=shape_map,
        warning_count=len(warning_shapes),
    )


def test_summarize_validation_aggregates_sources() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    article_shape = URIRef("https://shape.example/article")
    product_shape = URIRef("https://shape.example/product")
    result = _make_validation_result(
        conforms=False,
        warning_shapes=[article_shape],
        error_shapes=[article_shape, product_shape],
        shape_map={article_shape: "google-article", product_shape: "google-product"},
    )
    summary = protocol._summarize_validation(result)
    assert summary == {
        "total": 1,
        "pass": False,
        "fail": True,
        "warnings": {"count": 1, "sources": {"google-article": 1}},
        "errors": {
            "count": 2,
            "sources": {"google-article": 1, "google-product": 1},
        },
    }


@pytest.mark.asyncio
async def test_profile_protocol_emits_progress_and_validation_in_warn_mode() -> None:
    events: list[dict[str, object]] = []
    profile = _make_profile_with_overrides(
        settings={
            "shacl_validate_mode": "warn",
        }
    )
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=profile,
        root_dir=Path.cwd(),
        on_progress=lambda payload: events.append(payload),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_dataset_scoped_graph()
    )
    protocol._validate_graph = MagicMock(
        return_value=_make_validation_result(
            conforms=False,
            warning_shapes=[URIRef("https://shape.example/w")],
            error_shapes=[URIRef("https://shape.example/e")],
            shape_map={
                URIRef("https://shape.example/w"): "google-article",
                URIRef("https://shape.example/e"): "google-product",
            },
        )
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    assert events
    payload = events[-1]
    assert payload["kind"] == "graph"
    assert payload["url"] == "https://example.com/page"
    assert payload["validation"] == {
        "total": 1,
        "pass": False,
        "fail": True,
        "warnings": {"count": 1, "sources": {"google-article": 1}},
        "errors": {"count": 1, "sources": {"google-product": 1}},
    }
    summary = protocol.get_kpi_summary()
    assert summary["validation"] == {
        "total": 1,
        "pass": 0,
        "fail": 1,
        "warnings": {"count": 1, "sources": {"google-article": 1}},
        "errors": {"count": 1, "sources": {"google-product": 1}},
    }
    assert summary["validation"]["total"] == (
        summary["validation"]["pass"] + summary["validation"]["fail"]
    )


@pytest.mark.asyncio
async def test_profile_protocol_validation_fail_mode_raises() -> None:
    events: list[dict[str, object]] = []
    profile = _make_profile_with_overrides(
        settings={
            "shacl_validate_mode": "fail",
        }
    )
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=profile,
        root_dir=Path.cwd(),
        on_progress=lambda payload: events.append(payload),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_dataset_scoped_graph()
    )
    protocol._validate_graph = MagicMock(
        return_value=_make_validation_result(conforms=False)
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    with pytest.raises(RuntimeError, match="SHACL validation failed"):
        await protocol.callback(response)
    assert len(events) == 1
    assert events[0]["kind"] == "graph"
    assert events[0]["url"] == "https://example.com/page"
    assert events[0]["validation"] is not None
    assert events[0]["validation"]["pass"] is False
    protocol.patcher.patch_all.assert_not_called()


@pytest.mark.asyncio
async def test_profile_protocol_emits_null_validation_when_disabled() -> None:
    events: list[dict[str, object]] = []
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_overrides(settings={"shacl_validate_mode": "off"}),
        root_dir=Path.cwd(),
        on_progress=lambda payload: events.append(payload),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_dataset_scoped_graph()
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    assert len(events) == 1
    assert events[0]["kind"] == "graph"
    assert events[0]["validation"] is None
    summary = protocol.get_kpi_summary()
    assert summary["validation"] is None


@pytest.mark.asyncio
async def test_profile_protocol_passes_import_hash_mode_to_patcher() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_overrides(settings={"import_hash_mode": "off"}),
        root_dir=Path.cwd(),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_dataset_scoped_graph()
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)
    protocol.patcher.patch_all.assert_awaited_once()
    assert protocol.patcher.patch_all.call_args.kwargs["import_hash_mode"] == "off"


@pytest.mark.asyncio
async def test_profile_protocol_emits_graph_and_static_template_events() -> None:
    events: list[dict[str, object]] = []
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
        on_progress=lambda payload: events.append(payload),
    )
    template_graph = Graph()
    template_subject = URIRef("https://data.example.com/dataset/entities/template")
    template_graph.add((template_subject, RDF.type, URIRef("https://schema.org/Thing")))
    protocol._template_graph = template_graph
    protocol._template_exports = {}
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_dataset_scoped_graph()
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    assert [event["kind"] for event in events] == ["static_templates", "graph"]


@pytest.mark.asyncio
async def test_profile_protocol_collects_run_level_kpis() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_overrides(settings={"shacl_validate_mode": "off"}),
        root_dir=Path.cwd(),
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._core_ids.process_graph = MagicMock(side_effect=lambda g, _: g)
    protocol._apply_postprocessors = MagicMock(side_effect=lambda g, *_: g)
    protocol.patcher.patch_all = AsyncMock()
    protocol.rml_service.apply_mapping = AsyncMock(
        return_value=_make_dataset_scoped_graph()
    )

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    summary = protocol.get_kpi_summary()
    assert summary["profile"] == "test-profile"
    assert summary["totals"] == {
        "total_entities": 2,
        "type_assertions_total": 3,
        "property_assertions_total": 5,
    }
    assert summary["entities_by_type"] == {
        "https://schema.org/Article": 1,
        "https://schema.org/CreativeWork": 1,
        "https://schema.org/WebPage": 1,
    }
    assert summary["properties_by_predicate"] == {
        "https://schema.org/headline": 1,
        "https://schema.org/mainEntity": 1,
        "https://schema.org/name": 1,
        "https://w3id.org/seovoc/source": 2,
    }
    assert summary["validation"] is None


def test_protocol_validation_mode_normalization_and_deprecation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        strict_protocol = ProfileImportProtocol(
            context=_make_context(),
            profile=_make_profile_with_overrides(
                settings={"shacl_validate_mode": "strict"}
            ),
            root_dir=Path.cwd(),
        )
    assert strict_protocol._shacl_mode == "fail"
    assert "Deprecated SHACL validation mode 'strict' detected" in caplog.text

    with caplog.at_level("WARNING"):
        unknown_protocol = ProfileImportProtocol(
            context=_make_context(),
            profile=_make_profile_with_overrides(
                settings={"shacl_validate_mode": "invalid-mode"}
            ),
            root_dir=Path.cwd(),
        )
    assert unknown_protocol._shacl_mode == "warn"
    assert "Unsupported SHACL validation mode" in caplog.text

    with caplog.at_level("WARNING"):
        unknown_hash_mode = ProfileImportProtocol(
            context=_make_context(),
            profile=_make_profile_with_overrides(
                settings={"import_hash_mode": "invalid-mode"}
            ),
            root_dir=Path.cwd(),
        )
    assert unknown_hash_mode._import_hash_mode == "on"
    assert "Unsupported import hash mode" in caplog.text

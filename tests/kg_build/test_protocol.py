import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from jinja2 import UndefinedError
from rdflib import BNode, Graph, Literal, RDF, URIRef
from wordlift_client import WebPage, WebPageScrapeResponse

from wordlift_sdk.kg_build.config.loader import ProfileDefinition, ProfileMappingRoute
import wordlift_sdk.kg_build.protocol as protocol_module
from wordlift_sdk.kg_build.protocol import (
    ProfileImportProtocol,
    _path_contains_part,
    _resolve_postprocessor_runtime,
)
from wordlift_sdk.kg_build.rml_mapping import MappingResult
from wordlift_sdk.kg_build.postprocessors.types import PostprocessorResult
from wordlift_sdk.kg_build.postprocessors.processors.graph_annotation import (
    ImportAnnotationPostprocessor,
)
from wordlift_sdk.kg_build.postprocessors.processors.id_postprocessor import (
    CanonicalIdsPostprocessor,
    RootIdReconcilerPostprocessor,
    _find_web_page_iri as _find_web_page_iri_impl,
)
from wordlift_sdk.validation.shacl_validation_service import ValidationOutcome


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
        graph_queue=SimpleNamespace(put=AsyncMock(), close=AsyncMock()),
        configuration_provider=SimpleNamespace(
            get_value=lambda *_args, **_kwargs: None
        ),
    )


def _make_context_without_dataset() -> SimpleNamespace:
    return SimpleNamespace(
        account=SimpleNamespace(dataset_uri=None),
        client_configuration=SimpleNamespace(api_key={}),
        graph_queue=SimpleNamespace(put=AsyncMock(), close=AsyncMock()),
        configuration_provider=SimpleNamespace(
            get_value=lambda *_args, **_kwargs: None
        ),
    )


def _make_mapping_result(graph: Graph) -> MappingResult:
    return MappingResult(graph=graph, queue_wait_ms=0, mapping_ms=0)


def _make_validation_outcome(
    *,
    passed: bool,
    warning_sources: dict | None = None,
    error_sources: dict | None = None,
) -> ValidationOutcome:
    return ValidationOutcome(
        passed=passed,
        warning_sources=warning_sources or {},
        error_sources=error_sources or {},
        queue_wait_ms=0,
        validation_ms=0,
    )


def test_build_pp_context_injects_url_iri_lookup() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path("."),
    )
    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/article", html="<html></html>")
    )

    context = protocol._build_pp_context(
        "https://example.com/article",
        response,
        "https://data.example.com/dataset/articles/existing-article",
        "existing-hash",
    )
    lookup = context.extensions.get("kg_build.iri_lookup")

    assert lookup is not None

    graph = Graph()
    subject = URIRef("https://example.com/article#node")
    faq_page = URIRef("https://example.com/article#faq")
    graph.add((subject, RDF.type, URIRef("http://schema.org/Article")))
    graph.add(
        (
            subject,
            URIRef("http://schema.org/url"),
            Literal("https://example.com/article"),
        )
    )
    graph.add((faq_page, RDF.type, URIRef("http://schema.org/FAQPage")))
    graph.add((subject, URIRef("http://schema.org/subjectOf"), faq_page))
    graph.add((faq_page, URIRef("http://schema.org/about"), subject))
    assert (
        lookup.iri_for_subject(graph, subject)
        == "https://data.example.com/dataset/articles/existing-article"
    )

    output = CanonicalIdsPostprocessor(strategy="dependency_graph").process_graph(
        graph, context
    )
    assert (
        URIRef("https://data.example.com/dataset/articles/existing-article"),
        RDF.type,
        URIRef("http://schema.org/Article"),
    ) in output
    assert (
        URIRef(
            "https://data.example.com/dataset/articles/existing-article/faq-pages/faq-page"
        ),
        URIRef("http://schema.org/about"),
        URIRef("https://data.example.com/dataset/articles/existing-article"),
    ) in output


def _passthrough_pp() -> AsyncMock:
    return AsyncMock(
        side_effect=lambda g, url, resp, ewi, eih: PostprocessorResult(
            graph=g, queue_wait_ms=0, postprocessors_ms=0
        )
    )


def _annotating_pp(
    dataset_uri: str = "https://data.example.com/dataset",
    import_hash_mode: str = "on",
) -> AsyncMock:
    async def _stage(graph, url, resp, ewi, eih):
        ctx = SimpleNamespace(
            account=SimpleNamespace(dataset_uri=dataset_uri),
            existing_import_hash=eih,
            import_hash_mode=import_hash_mode,
        )
        g = ImportAnnotationPostprocessor().process_graph(graph, ctx)
        return PostprocessorResult(graph=g, queue_wait_ms=0, postprocessors_ms=0)

    return AsyncMock(side_effect=_stage)


def _reconciling_pp(
    dataset_uri: str = "https://data.example.com/dataset",
) -> AsyncMock:
    async def _stage(graph, url, resp, ewi, eih):
        ctx = SimpleNamespace(
            account=SimpleNamespace(dataset_uri=dataset_uri),
            existing_import_hash=eih,
            import_hash_mode="on",
            existing_web_page_id=ewi,
        )
        g = RootIdReconcilerPostprocessor().process_graph(graph, ctx)
        g = ImportAnnotationPostprocessor().process_graph(g, ctx)
        return PostprocessorResult(graph=g, queue_wait_ms=0, postprocessors_ms=0)

    return AsyncMock(side_effect=_stage)


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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(
            _make_graph("https://example.com/mapped-web-page")
        )
    )
    protocol._run_postprocessing_stage = _reconciling_pp()
    protocol.patcher.patch_all = AsyncMock()

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
async def test_profile_protocol_put_strategy_writes_to_graph_queue() -> None:
    context = _make_context()
    protocol = ProfileImportProtocol(
        context=context,
        profile=_make_profile(),
        root_dir=Path.cwd(),
        graph_write_strategy="put",
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )

    await protocol.callback(response)

    context.graph_queue.put.assert_awaited_once()
    protocol.patcher.patch_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_static_templates_use_graph_queue_when_put_strategy_enabled() -> None:
    context = _make_context()
    protocol = ProfileImportProtocol(
        context=context,
        profile=_make_profile(),
        root_dir=Path.cwd(),
        graph_write_strategy="put",
    )
    protocol._template_graph = _make_dataset_scoped_graph()
    protocol._template_exports = {}
    protocol._shacl_validator.validate = AsyncMock(return_value=None)
    protocol._emit_progress = MagicMock()
    protocol._kpi.record_graph = MagicMock()
    protocol.patcher.patch_all = AsyncMock()

    await protocol._patch_static_templates_once()

    context.graph_queue.put.assert_awaited_once_with(protocol._template_graph)
    protocol.patcher.patch_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_protocol_put_strategy_honors_import_hash_write_mode() -> None:
    context = _make_context()
    protocol = ProfileImportProtocol(
        context=context,
        profile=_make_profile_with_overrides(settings={"import_hash_mode": "write"}),
        root_dir=Path.cwd(),
        graph_write_strategy="put",
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()
    graph = _make_dataset_scoped_graph()
    child = URIRef("https://data.example.com/dataset/entities/article-1/faq/1")
    graph.add(
        (
            URIRef("https://data.example.com/dataset/entities/article-1"),
            URIRef("https://schema.org/hasPart"),
            child,
        )
    )
    graph.add((child, RDF.type, URIRef("https://schema.org/Question")))
    protocol._run_mapping_stage = AsyncMock(return_value=_make_mapping_result(graph))

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    queued_graph = context.graph_queue.put.await_args.args[0]
    for subject in (URIRef("https://data.example.com/dataset/web-pages/1"),):
        values = list(
            queued_graph.objects(subject, URIRef("https://w3id.org/seovoc/importHash"))
        )
        assert len(values) == 1
        assert str(values[0]).strip()
    assert not list(
        queued_graph.objects(child, URIRef("https://w3id.org/seovoc/importHash"))
    )


@pytest.mark.asyncio
async def test_profile_protocol_put_strategy_skips_when_import_hash_matches() -> None:
    context = _make_context()
    protocol = ProfileImportProtocol(
        context=context,
        profile=_make_profile(),
        root_dir=Path.cwd(),
        graph_write_strategy="put",
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    graph = _make_dataset_scoped_graph()
    # Pre-annotate so the expected hash matches what the pipeline will produce
    ann_ctx = SimpleNamespace(
        account=context.account,
        existing_import_hash=None,
        import_hash_mode="on",
    )
    ImportAnnotationPostprocessor().process_graph(graph, ann_ctx)
    expected_hash = protocol.patcher._compute_import_hash(
        URIRef("https://data.example.com/dataset/web-pages/1"),
        graph,
        "https://data.example.com/dataset",
    )
    protocol._run_mapping_stage = AsyncMock(return_value=_make_mapping_result(graph))
    protocol._run_postprocessing_stage = _annotating_pp()
    protocol.patcher.patch_all = AsyncMock()

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response, existing_import_hash=expected_hash)

    context.graph_queue.put.assert_not_awaited()
    protocol.patcher.patch_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_protocol_put_strategy_honors_import_hash_off_mode() -> None:
    context = _make_context()
    protocol = ProfileImportProtocol(
        context=context,
        profile=_make_profile_with_overrides(settings={"import_hash_mode": "off"}),
        root_dir=Path.cwd(),
        graph_write_strategy="put",
    )
    protocol._patch_static_templates_once = AsyncMock()
    protocol._resolve_mapping_path = MagicMock(return_value=Path("mapping.yarrrml"))
    protocol._get_mapping_content = MagicMock(return_value="mapping")
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    queued_graph = context.graph_queue.put.await_args.args[0]
    assert not list(
        queued_graph.triples((None, URIRef("https://w3id.org/seovoc/importHash"), None))
    )


def test_protocol_rejects_unknown_graph_write_strategy() -> None:
    with pytest.raises(ValueError, match="Unsupported graph_write_strategy: invalid"):
        ProfileImportProtocol(
            context=_make_context(),
            profile=_make_profile(),
            root_dir=Path.cwd(),
            graph_write_strategy="invalid",
        )


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
    mapped_subject = "https://example.com/mapped-web-page"
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_graph(mapped_subject))
    )
    protocol._run_postprocessing_stage = _annotating_pp()
    protocol.patcher.patch_all = AsyncMock()

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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_multi_entity_graph())
    )
    protocol._run_postprocessing_stage = _annotating_pp()
    protocol.patcher.patch_all = AsyncMock()

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

    async def _pp_with_injection(graph, url, resp, ewi, eih):
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
        ctx = SimpleNamespace(
            account=SimpleNamespace(dataset_uri="https://data.example.com/dataset"),
            extensions=None,
        )
        g = CanonicalIdsPostprocessor().process_graph(graph, ctx)
        return PostprocessorResult(graph=g, queue_wait_ms=0, postprocessors_ms=0)

    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(mapped_graph)
    )
    protocol._run_postprocessing_stage = AsyncMock(side_effect=_pp_with_injection)

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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_multi_entity_graph())
    )
    protocol._run_postprocessing_stage = _annotating_pp()
    protocol.patcher.patch_all = AsyncMock()

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
    protocol._run_postprocessing_stage = _annotating_pp()
    protocol.patcher.patch_all = AsyncMock()

    graph = Graph()
    article = URIRef("https://example.com/entities/article-only")
    graph.add((article, RDF.type, URIRef("http://schema.org/Article")))
    graph.add((article, URIRef("http://schema.org/headline"), Literal("Title")))
    protocol._run_mapping_stage = AsyncMock(return_value=_make_mapping_result(graph))

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
    protocol._run_postprocessing_stage = _annotating_pp()
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
    protocol._run_mapping_stage = AsyncMock(return_value=_make_mapping_result(graph))

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
    protocol._run_postprocessing_stage = _annotating_pp()
    protocol.patcher.patch_all = AsyncMock()

    graph = Graph()
    article = URIRef("https://example.com/entities/article")
    blank = BNode()
    graph.add((article, RDF.type, URIRef("http://schema.org/Article")))
    graph.add((blank, RDF.type, URIRef("http://schema.org/Thing")))
    graph.add((article, URIRef("http://schema.org/mentions"), blank))
    protocol._run_mapping_stage = AsyncMock(return_value=_make_mapping_result(graph))

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
    ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_settings({"POSTPROCESSOR_RUNTIME": "persistent"}),
        root_dir=Path.cwd(),
    )
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
        "https://example.com/page",
        response,
        existing_web_page_id=None,
        existing_import_hash=None,
    )

    assert context.account_key == "profile-secret"
    assert context.profile["name"] == "test-profile"
    assert context.profile["settings"]["api_url"] == "https://profile-api.example.com"


@pytest.mark.parametrize(
    "language,prefix", [("de", "mueller-"), ("tr", "muller-"), (None, "muller-")]
)
def test_build_pp_context_uses_account_language_for_ids(language, prefix) -> None:
    host_context = _make_context()
    host_context.account.language = language
    protocol = ProfileImportProtocol(
        context=host_context, profile=_make_profile(), root_dir=Path.cwd()
    )
    context = protocol._build_pp_context(
        "https://example.com/page",
        WebPageScrapeResponse(web_page=WebPage(url="https://example.com/page")),
        existing_web_page_id=None,
        existing_import_hash=None,
    )
    assert context.account is host_context.account
    iri = context.ids.new_independent(Graph(), type_name="Thing", base_value="Müller")
    assert str(iri).startswith(f"https://data.example.com/dataset/things/{prefix}")


def test_build_pp_context_preserves_custom_profile_settings() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_settings(
            {
                "api_url": "https://profile-api.example.com",
                "disable_article_markup": True,
            }
        ),
        root_dir=Path.cwd(),
    )
    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )

    context = protocol._build_pp_context(
        "https://example.com/page",
        response,
        existing_web_page_id=None,
        existing_import_hash=None,
    )

    assert context.profile["settings"]["disable_article_markup"] is True


def test_account_key_resolved_from_profile_api_key() -> None:
    profile = ProfileDefinition(
        **{
            **_make_profile().__dict__,
            "api_key": "profile-secret",
        }
    )
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=profile,
        root_dir=Path.cwd(),
    )
    assert protocol._account_key == "profile-secret"


def test_account_key_is_none_when_no_key_configured() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    assert protocol._account_key is None


def test_protocol_helpers_runtime_and_path_part() -> None:
    assert _path_contains_part("profiles/_base/templates", "_base") is True
    assert _path_contains_part("profiles/demo/templates", "_base") is False
    assert _resolve_postprocessor_runtime({}) == "persistent"
    assert (
        _resolve_postprocessor_runtime({"POSTPROCESSOR_RUNTIME": "persistent"})
        == "persistent"
    )
    assert protocol_module._resolve_materialization_backend({}) == "morph"
    assert (
        protocol_module._resolve_materialization_backend(
            {"MATERIALIZATION_BACKEND": "worph"}
        )
        == "worph"
    )


def test_protocol_initializes_materialization_pool_with_selected_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_init_pool(max_workers: int, backend: str = "morph") -> None:
        captured["max_workers"] = max_workers
        captured["backend"] = backend

    monkeypatch.setattr(protocol_module, "init_materialization_pool", _fake_init_pool)
    ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile_with_settings(
            {
                "mapping_pool_size": 3,
                "materialization_backend": "worph",
            }
        ),
        root_dir=Path.cwd(),
    )

    assert captured == {"max_workers": 3, "backend": "worph"}


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
    protocol._run_mapping_stage = AsyncMock(return_value=_make_mapping_result(Graph()))
    protocol.patcher.patch_all = AsyncMock()

    response = WebPageScrapeResponse(
        web_page=WebPage(url="https://example.com/page", html="<html></html>")
    )
    await protocol.callback(response)

    protocol.patcher.patch_all.assert_not_called()


def test_close_invokes_postprocessor_service_close() -> None:
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    mock_close = MagicMock()
    protocol._postprocessor_service.close = mock_close
    asyncio.run(protocol.close())
    mock_close.assert_called_once()


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


def test_postprocessor_factory_builds_required_processors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the factory used by PostprocessorService includes the standard processors."""

    def fake_loader(*, root_dir, profile_name, runtime=None):
        return []

    monkeypatch.setattr(protocol_module, "load_postprocessors_for_profile", fake_loader)
    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=Path.cwd(),
    )
    # Get one slot from the pool to inspect the processors
    processors = list(protocol._postprocessor_service._queue.get_nowait())
    names = [p.name for p in processors]
    assert "root_id_reconciler" in names
    assert "canonical_ids" in names
    assert "import_annotation" in names


def test_resolve_account_key_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _make_profile()
    context = _make_context()

    profile_with_key = ProfileDefinition(
        **{**profile.__dict__, "api_key": "profile-key"}
    )
    assert (
        protocol_module._resolve_account_key(profile_with_key, context) == "profile-key"
    )

    context.client_configuration.api_key = {"ApiKey": "runtime-key"}
    assert protocol_module._resolve_account_key(profile, context) == "runtime-key"

    context.client_configuration.api_key = {}
    context.configuration_provider = SimpleNamespace(
        get_value=lambda name: "provider-key" if name == "WORDLIFT_KEY" else None
    )
    assert protocol_module._resolve_account_key(profile, context) == "provider-key"

    context.configuration_provider = SimpleNamespace(
        get_value=lambda _name: (_ for _ in ()).throw(RuntimeError("nope"))
    )
    monkeypatch.setenv("WORDLIFT_API_KEY", "env-key")
    assert protocol_module._resolve_account_key(profile, context) == "env-key"
    monkeypatch.delenv("WORDLIFT_API_KEY", raising=False)


def test_clean_key_write_debug_and_reconcile(tmp_path: Path) -> None:
    assert protocol_module._clean_key(None) is None
    assert protocol_module._clean_key("  ") is None
    assert protocol_module._clean_key(" x ") == "x"

    protocol = ProfileImportProtocol(
        context=_make_context(),
        profile=_make_profile(),
        root_dir=tmp_path,
        debug_dir=tmp_path / "debug",
    )
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
    assert _find_web_page_iri_impl(https_graph) == old
    ctx = SimpleNamespace(
        existing_web_page_id=str(new),
        account=SimpleNamespace(dataset_uri=""),
        existing_import_hash=None,
        import_hash_mode="on",
    )
    RootIdReconcilerPostprocessor().process_graph(https_graph, ctx)
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

    async def _mapping_stage(response, url, ewi, debug_output):
        if isinstance(debug_output, dict):
            debug_output["xhtml"] = "<html><body>Converted</body></html>"
        return _make_mapping_result(_make_graph("https://example.com/mapped-web-page"))

    protocol._run_mapping_stage = AsyncMock(side_effect=_mapping_stage)
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()

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
    assert protocol._shacl_validator.mode.value == "warn"
    assert protocol._import_hash_mode == "write"
    assert protocol_module._resolve_list_setting(["a", " ", "b"]) == ["a", "b"]
    assert protocol_module._resolve_list_setting(123) == ["123"]

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
    protocol._shacl_validator.validate = AsyncMock(
        return_value=_make_validation_outcome(passed=False)
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
    graph = Graph()
    graph.add(
        (
            URIRef("https://example.com/entities/x"),
            RDF.type,
            URIRef("https://schema.org/Thing"),
        )
    )
    assert _find_web_page_iri_impl(graph) is None


def test_validation_outcome_to_dict_aggregates_sources() -> None:
    outcome = _make_validation_outcome(
        passed=False,
        warning_sources={"google-article": 1},
        error_sources={"google-article": 1, "google-product": 1},
    )
    summary = outcome.to_dict()
    assert summary == {
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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()
    protocol._shacl_validator.validate = AsyncMock(
        return_value=_make_validation_outcome(
            passed=False,
            warning_sources={"google-article": 1},
            error_sources={"google-product": 1},
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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()
    protocol._shacl_validator.validate = AsyncMock(
        return_value=_make_validation_outcome(passed=False)
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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()

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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()

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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _passthrough_pp()
    protocol.patcher.patch_all = AsyncMock()

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
    protocol._run_mapping_stage = AsyncMock(
        return_value=_make_mapping_result(_make_dataset_scoped_graph())
    )
    protocol._run_postprocessing_stage = _annotating_pp()
    protocol.patcher.patch_all = AsyncMock()

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
    assert strict_protocol._shacl_validator.mode.value == "fail"
    assert "Deprecated SHACL validation mode 'strict' detected" in caplog.text

    with caplog.at_level("WARNING"):
        unknown_protocol = ProfileImportProtocol(
            context=_make_context(),
            profile=_make_profile_with_overrides(
                settings={"shacl_validate_mode": "invalid-mode"}
            ),
            root_dir=Path.cwd(),
        )
    assert unknown_protocol._shacl_validator.mode.value == "warn"
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

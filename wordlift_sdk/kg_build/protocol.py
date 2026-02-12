from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from rdflib import Graph, RDF, URIRef
from wordlift_client.models.web_page_import_response import WebPageImportResponse
from wordlift_sdk.protocol import Context
from wordlift_sdk.protocol.web_page_import_protocol import (
    WebPageImportProtocolInterface,
)

from .config import ProfileDefinition
from .entity_patcher import EntityPatcher
from .id_allocator import IdAllocator
from .id_postprocessor import CanonicalIdsPostprocessor
from .postprocessors import PostprocessorContext, load_postprocessors_for_profile
from .rml_mapping import RmlMappingService
from .templates import JinjaRdfTemplateReifier, TemplateTextRenderer

logger = logging.getLogger(__name__)


class ProfileImportProtocol(WebPageImportProtocolInterface):
    """Generic cloud callback protocol driven by profile mappings and templates."""

    def __init__(
        self,
        context: Context,
        profile: ProfileDefinition,
        root_dir: Path | None = None,
        debug_dir: Path | None = None,
    ) -> None:
        super().__init__(context)
        self.profile = profile
        self.root_dir = root_dir or Path.cwd()
        self.debug_dir = debug_dir

        self.profile_dir = self.root_dir / "profiles" / self.profile.name
        self.templates_dir = self._resolve_path(self.profile.templates_dir)
        self.mappings_dir = self._resolve_path(self.profile.mappings_dir)

        self.rml_service = RmlMappingService(context)
        self.patcher = EntityPatcher(context)
        self.template_reifier = JinjaRdfTemplateReifier(self.templates_dir)
        self.text_renderer = TemplateTextRenderer()

        self._template_graph: Graph | None = None
        self._template_exports: dict[str, Any] | None = None
        self._mapping_cache: dict[Path, str] = {}
        self._static_templates_patched = False
        self._core_ids = CanonicalIdsPostprocessor()
        self._postprocessors = load_postprocessors_for_profile(
            root_dir=self.root_dir,
            profile_name=self.profile.name,
        )

    async def callback(self, response: WebPageImportResponse) -> None:
        url = (
            response.web_page.url
            if hasattr(response, "web_page") and response.web_page
            else "Unknown URL"
        )

        if hasattr(response, "errors") and response.errors:
            logger.error("Cloud callback error for %s: %s", url, response.errors)
            return

        if not response.web_page or not response.web_page.html:
            logger.warning("No HTML content for %s, skipping mapping", url)
            return

        root_id = response.id
        if not root_id:
            logger.warning("No root ID for %s, skipping mapping", url)
            return

        await self._patch_static_templates_once()

        mapping_path = self._resolve_mapping_path(url)
        rendered_mapping = self._get_mapping_content(mapping_path)

        graph = await self.rml_service.apply_mapping(
            html=response.web_page.html,
            url=url,
            mapping_file_path=mapping_path,
            mapping_content=rendered_mapping,
            response=response,
        )
        if not graph or len(graph) == 0:
            logger.warning("No triples produced for %s", url)
            return

        self._reconcile_root_id(graph, root_id)
        graph = self._core_ids.process_graph(
            graph, self._build_pp_context(url, response)
        )
        graph = self._apply_postprocessors(graph, url, response)

        if self.debug_dir:
            self._write_debug_graph(graph, url)

        await self.patcher.patch_all(graph)
        logger.info("Patched %s triples for %s", len(graph), url)

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return self.root_dir / path

    def _resolve_mapping_path(self, url: str) -> Path:
        mapping = self.profile.resolve_mapping(url)
        path = Path(mapping)
        if path.is_absolute():
            return path
        return self.mappings_dir / path

    async def _patch_static_templates_once(self) -> None:
        if self._static_templates_patched:
            return

        self._ensure_templates_loaded()
        if self._template_graph and len(self._template_graph) > 0:
            await self.patcher.patch_all(self._template_graph)
            if self.debug_dir:
                static_debug = self.debug_dir / "static_templates.ttl"
                static_debug.parent.mkdir(parents=True, exist_ok=True)
                self._template_graph.serialize(
                    destination=static_debug, format="turtle"
                )
            logger.info("Patched %s static template triples", len(self._template_graph))

        self._static_templates_patched = True

    def _ensure_templates_loaded(self) -> None:
        if self._template_graph is not None and self._template_exports is not None:
            return

        dataset_uri = getattr(self.context.account, "dataset_uri", None)
        if not dataset_uri:
            raise RuntimeError("Dataset URI not available on context.account.")

        base_context = {
            "account": self.context.account,
            "dataset_uri": str(dataset_uri).rstrip("/"),
        }
        exports = self.text_renderer.load_exports(self.profile_dir, base_context)
        context = {**base_context, "exports": exports}

        self._template_exports = exports
        self._template_graph = (
            self.template_reifier.reify(context)
            if self.template_reifier.has_templates()
            else Graph()
        )

        logger.info(
            "Loaded %s static template triples and %s exports for profile '%s'",
            len(self._template_graph),
            len(self._template_exports),
            self.profile.name,
        )

    def _get_mapping_content(self, mapping_path: Path) -> str:
        cached = self._mapping_cache.get(mapping_path)
        if cached is not None:
            return cached

        dataset_uri = getattr(self.context.account, "dataset_uri", None)
        if not dataset_uri:
            raise RuntimeError("Dataset URI not available on context.account.")

        self._ensure_templates_loaded()

        context = {
            "account": self.context.account,
            "dataset_uri": str(dataset_uri).rstrip("/"),
            "exports": self._template_exports or {},
        }
        template_path = self.text_renderer.resolve_mapping_template(mapping_path)
        rendered = self.text_renderer.render_file(template_path, context)
        self._mapping_cache[mapping_path] = rendered
        return rendered

    def _apply_postprocessors(
        self,
        graph: Graph,
        url: str,
        response: WebPageImportResponse,
    ) -> Graph:
        if not self._postprocessors:
            return graph

        pp_context = self._build_pp_context(url, response)

        for processor in self._postprocessors:
            graph = processor.run(graph, pp_context)
            logger.info("Applied postprocessor '%s' for %s", processor.name, url)
        return graph

    def _build_pp_context(
        self, url: str, response: WebPageImportResponse
    ) -> PostprocessorContext:
        dataset_uri = str(getattr(self.context.account, "dataset_uri", "")).rstrip("/")
        ids = IdAllocator(dataset_uri) if dataset_uri else None
        return PostprocessorContext(
            profile_name=self.profile.name,
            url=url,
            account=self.context.account,
            exports=self._template_exports or {},
            response=response,
            settings=dict(self.profile.settings),
            ids=ids,
        )

    def _write_debug_graph(self, graph: Graph, url: str) -> None:
        assert self.debug_dir is not None
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = hashlib.sha256(url.encode("utf-8")).hexdigest()
        debug_file = self.debug_dir / f"cloud_{safe_name}.ttl"
        graph.serialize(destination=debug_file, format="turtle")

    def _reconcile_root_id(self, graph: Graph, root_id: str) -> None:
        old_iri = self._find_web_page_iri(graph)
        if old_iri and str(old_iri) != root_id:
            self._swap_iris(graph, old_iri, URIRef(root_id))

    def _find_web_page_iri(self, graph: Graph) -> URIRef | None:
        for subject in graph.subjects(RDF.type, URIRef("http://schema.org/WebPage")):
            return subject
        for subject in graph.subjects(RDF.type, URIRef("https://schema.org/WebPage")):
            return subject
        return None

    def _swap_iris(self, graph: Graph, old_iri: URIRef, new_iri: URIRef) -> None:
        for subject, predicate, obj in list(graph.triples((old_iri, None, None))):
            graph.remove((subject, predicate, obj))
            graph.add((new_iri, predicate, obj))
        for subject, predicate, obj in list(graph.triples((None, None, old_iri))):
            graph.remove((subject, predicate, obj))
            graph.add((subject, predicate, new_iri))

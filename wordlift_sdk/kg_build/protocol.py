from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jinja2 import UndefinedError
from rdflib import Graph, Literal, RDF, URIRef
from wordlift_client.models.web_page_scrape_response import WebPageScrapeResponse
from wordlift_sdk.protocol import Context
from wordlift_sdk.protocol.web_page_import_protocol import (
    WebPageImportProtocolInterface,
)
from wordlift_sdk.validation.shacl import (
    ValidationResult,
    resolve_shape_specs,
    validate_file,
)

from .config import ProfileDefinition
from .entity_patcher import EntityPatcher
from .id_allocator import IdAllocator
from .id_postprocessor import CanonicalIdsPostprocessor
from .kpi import KgBuildKpiCollector
from .postprocessors import (
    PostprocessorContext,
    close_loaded_postprocessors,
    load_postprocessors_for_profile,
)
from .rml_mapping import RmlMappingService
from .templates import JinjaRdfTemplateReifier, TemplateTextRenderer

logger = logging.getLogger(__name__)
SEOVOC_SOURCE = URIRef("https://w3id.org/seovoc/source")
SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")


def _path_contains_part(path: str, part: str) -> bool:
    return part in Path(path).parts


def _resolve_postprocessor_runtime(settings: dict[str, Any]) -> str:
    value = settings.get("postprocessor_runtime")
    if value is None:
        value = settings.get("POSTPROCESSOR_RUNTIME")
    return str(value or "persistent")


class ProfileImportProtocol(WebPageImportProtocolInterface):
    """Generic cloud callback protocol driven by profile mappings and templates."""

    def __init__(
        self,
        context: Context,
        profile: ProfileDefinition,
        root_dir: Path | None = None,
        debug_dir: Path | None = None,
        on_progress: Any | None = None,
        graph_write_strategy: str = "patch",
    ) -> None:
        super().__init__(context)
        if graph_write_strategy not in {"patch", "put"}:
            raise ValueError(
                f"Unsupported graph_write_strategy: {graph_write_strategy}"
            )
        self.profile = profile
        self.root_dir = root_dir or Path.cwd()
        self.debug_dir = debug_dir
        self._on_progress = on_progress
        self._graph_write_strategy = graph_write_strategy

        self.profile_dir = self.root_dir / "profiles" / self.profile.name
        self.templates_dir = self._resolve_path(self.profile.templates_dir)
        self.mappings_dir = self._resolve_path(self.profile.mappings_dir)
        self._template_dirs = self._resolve_overlay_paths(
            self.profile.template_overlay_dirs or (self.profile.templates_dir,)
        )
        self._mapping_dirs = self._resolve_overlay_paths(
            self.profile.mapping_overlay_dirs or (self.profile.mappings_dir,)
        )

        self.rml_service = RmlMappingService(context)
        self.patcher = EntityPatcher(context)
        self.template_reifier = JinjaRdfTemplateReifier(self._template_dirs)
        self.text_renderer = TemplateTextRenderer()

        self._template_graph: Graph | None = None
        self._template_exports: dict[str, Any] | None = None
        self._mapping_cache: dict[Path, str] = {}
        self._static_templates_patched = False
        self._static_templates_lock = asyncio.Lock()
        canonical_id_strategy = (
            str(
                self.profile.settings.get(
                    "canonical_id_strategy",
                    self.profile.settings.get("CANONICAL_ID_STRATEGY", "legacy"),
                )
            )
            .strip()
            .lower()
        )
        self._core_ids = CanonicalIdsPostprocessor(strategy=canonical_id_strategy)
        self._postprocessor_runtime = _resolve_postprocessor_runtime(
            dict(self.profile.settings)
        )
        logger.info(
            "Resolved postprocessor runtime for profile '%s': %s (origin=%s)",
            self.profile.name,
            self._postprocessor_runtime,
            self.profile.origins.get("postprocessor_runtime", "default"),
        )
        self._postprocessors = load_postprocessors_for_profile(
            root_dir=self.root_dir,
            profile_name=self.profile.name,
            runtime=self._postprocessor_runtime,
        )
        self._shacl_mode = self._resolve_validation_mode(
            self.profile.settings.get(
                "shacl_validate_mode",
                self.profile.settings.get("SHACL_VALIDATE_MODE", "warn"),
            )
        )
        shacl_builtin_shapes = self._resolve_list_setting(
            self.profile.settings.get(
                "shacl_builtin_shapes",
                self.profile.settings.get("SHACL_BUILTIN_SHAPES"),
            )
        )
        shacl_exclude_builtin_shapes = self._resolve_list_setting(
            self.profile.settings.get(
                "shacl_exclude_builtin_shapes",
                self.profile.settings.get("SHACL_EXCLUDE_BUILTIN_SHAPES"),
            )
        )
        shacl_extra_shapes = self._resolve_list_setting(
            self.profile.settings.get(
                "shacl_extra_shapes", self.profile.settings.get("SHACL_EXTRA_SHAPES")
            )
        )
        self._shacl_shape_specs = resolve_shape_specs(
            builtin_shapes=shacl_builtin_shapes or None,
            exclude_builtin_shapes=shacl_exclude_builtin_shapes or None,
            extra_shapes=shacl_extra_shapes or None,
        )
        self._import_hash_mode = self._resolve_import_hash_mode(
            self.profile.settings.get(
                "import_hash_mode",
                self.profile.settings.get("IMPORT_HASH_MODE", "on"),
            )
        )
        self._kpi = KgBuildKpiCollector(
            dataset_uri=getattr(self.context.account, "dataset_uri", None),
            validation_enabled=self._shacl_mode != "off",
        )
        logger.debug(
            "Resolved mappings for profile '%s': effective_dir=%s (origin=%s), routes=%s (origin=%s), overlay_dirs=%s",
            self.profile.name,
            self.mappings_dir,
            self.profile.origins.get("mappings_dir", "default"),
            len(self.profile.routes),
            self.profile.origins.get("routes", "default"),
            [str(p) for p in self._mapping_dirs],
        )

    async def callback(
        self,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None = None,
        existing_import_hash: str | None = None,
    ) -> None:
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

        await self._patch_static_templates_once()

        mapping_path = self._resolve_mapping_path(url)
        rendered_mapping = self._get_mapping_content(mapping_path)
        mapping_response = self._mapping_response(response, existing_web_page_id)
        debug_output: dict[str, str] | None = {} if self.debug_dir else None

        graph = await self.rml_service.apply_mapping(
            html=response.web_page.html,
            url=url,
            mapping_file_path=mapping_path,
            mapping_content=rendered_mapping,
            response=mapping_response,
            debug_output=debug_output,
        )
        if not graph or len(graph) == 0:
            logger.warning("No triples produced for %s", url)
            return

        if existing_web_page_id:
            self._reconcile_root_id(graph, existing_web_page_id)
        graph = self._apply_postprocessors(graph, url, response, existing_web_page_id)
        # Canonical IDs must run after custom postprocessors so any nodes minted
        # by local logic are normalized before graph sync patching.
        graph = self._core_ids.process_graph(
            graph, self._build_pp_context(url, response, existing_web_page_id)
        )
        self._set_source(graph, existing_web_page_id)
        self._set_existing_import_hash(graph, existing_import_hash)

        if self.debug_dir:
            xhtml = (debug_output or {}).get("xhtml")
            self._write_debug_source_documents(
                url=url, html=response.web_page.html, xhtml=xhtml
            )
            self._write_debug_graph(graph, url)

        validation_payload = self._validate_graph_if_enabled(graph, url)
        graph_metrics = self._kpi.graph_metrics(graph)
        self._emit_progress(
            {
                "kind": "graph",
                "profile": self.profile.name,
                "url": url,
                "graph": graph_metrics,
                "validation": validation_payload,
            }
        )
        self._kpi.record_graph(graph)
        if (
            validation_payload is not None
            and self._shacl_mode == "fail"
            and not validation_payload["pass"]
        ):
            raise RuntimeError(f"SHACL validation failed for {url} in fail mode.")
        await self._write_graph(graph)
        logger.info("Wrote %s triples for %s", len(graph), url)

    def close(self) -> None:
        close_loaded_postprocessors(self._postprocessors)

    def get_kpi_summary(self) -> dict[str, object]:
        return self._kpi.summary(self.profile.name)

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return self.root_dir / path

    def _resolve_overlay_paths(self, raw_paths: tuple[str, ...]) -> tuple[Path, ...]:
        return tuple(self._resolve_path(p) for p in raw_paths)

    def _resolve_mapping_path(self, url: str) -> Path:
        mapping = self.profile.resolve_mapping(url)
        path = Path(mapping)
        if path.is_absolute():
            return path
        for mapping_dir in reversed(self._mapping_dirs):
            candidate = mapping_dir / path
            if candidate.exists():
                return candidate
            templated = self.text_renderer.resolve_mapping_template(candidate)
            if templated.exists():
                return templated
        return self._mapping_dirs[-1] / path

    async def _patch_static_templates_once(self) -> None:
        if self._static_templates_patched:
            return
        async with self._static_templates_lock:
            if self._static_templates_patched:
                return

            self._ensure_templates_loaded()
            if self._template_graph and len(self._template_graph) > 0:
                validation_payload = self._validate_graph_if_enabled(
                    self._template_graph, "static_templates"
                )
                self._emit_progress(
                    {
                        "kind": "static_templates",
                        "profile": self.profile.name,
                        "graph": self._kpi.graph_metrics(self._template_graph),
                        "validation": validation_payload,
                    }
                )
                self._kpi.record_graph(self._template_graph)
                if (
                    validation_payload is not None
                    and self._shacl_mode == "fail"
                    and not validation_payload["pass"]
                ):
                    raise RuntimeError(
                        "SHACL validation failed for static templates in fail mode."
                    )
                await self._write_graph(self._template_graph)
                if self.debug_dir:
                    static_debug = self.debug_dir / "static_templates.ttl"
                    static_debug.parent.mkdir(parents=True, exist_ok=True)
                    self._template_graph.serialize(
                        destination=static_debug, format="turtle"
                    )
                logger.info(
                    "Wrote %s static template triples", len(self._template_graph)
                )

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
        exports, exports_summary = self.text_renderer.load_exports_with_summary(
            self._template_dirs, base_context
        )
        loaded_files = exports_summary.get("loaded_files", [])
        base_exports_loaded = any(
            isinstance(path, str) and _path_contains_part(path, "_base")
            for path in loaded_files
        )
        context = {**base_context, "exports": exports}

        self._template_exports = exports
        template_paths, template_summary = (
            self.template_reifier.resolve_template_paths()
        )
        try:
            self._template_graph = (
                self.template_reifier.reify(context) if template_paths else Graph()
            )
        except Exception as exc:
            if isinstance(exc, (UndefinedError, KeyError, AttributeError)):
                searched_paths = exports_summary.get("searched_paths", [])
                raise RuntimeError(
                    "Template rendering failed due to missing template context "
                    f"for profile '{self.profile.name}'. "
                    f"Original error: {exc}. "
                    f"Searched exports files: {searched_paths}. "
                    f"Loaded exports files: {loaded_files}. "
                    f"_base exports loaded: {base_exports_loaded}."
                ) from exc
            raise

        logger.info(
            "Template resolution for profile '%s': source_files=%s effective_files=%s overrides=%s",
            self.profile.name,
            template_summary["source_files"],
            template_summary["effective_files"],
            template_summary["overrides"],
        )
        logger.info(
            "Exports merge for profile '%s': source_keys=%s effective_keys=%s overrides=%s",
            self.profile.name,
            exports_summary["source_keys"],
            exports_summary["effective_keys"],
            exports_summary["overrides"],
        )
        logger.debug(
            "Exports lookup for profile '%s': searched=%s loaded=%s base_loaded=%s",
            self.profile.name,
            exports_summary.get("searched_paths", []),
            loaded_files,
            base_exports_loaded,
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

    async def _write_graph(self, graph: Graph) -> None:
        if self._graph_write_strategy == "put":
            if not self._prepare_graph_for_put(graph):
                return
            await self.context.graph_queue.put(graph)
            return
        await self.patcher.patch_all(graph, import_hash_mode=self._import_hash_mode)

    def _prepare_graph_for_put(self, graph: Graph) -> bool:
        dataset_uri = str(
            getattr(self.context.account, "dataset_uri", "") or ""
        ).rstrip("/")
        if not dataset_uri:
            return False

        subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(dataset_uri)
        }
        if not subjects:
            return False

        first_level_subjects = {
            subject
            for subject in self._first_level_subjects(graph)
            if subject in subjects
        }
        if not first_level_subjects:
            return False

        if self._import_hash_mode == "off":
            return True

        representative = next(iter(first_level_subjects))
        existing_hash = self.patcher._existing_import_hash(representative, graph)
        import_hash = self.patcher._compute_import_hash(
            representative, graph, dataset_uri
        )
        for subject in first_level_subjects:
            self.patcher._set_import_hash(subject, graph, import_hash)

        return not (
            self._import_hash_mode == "on"
            and existing_hash
            and existing_hash == import_hash
        )

    def _apply_postprocessors(
        self,
        graph: Graph,
        url: str,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
    ) -> Graph:
        if not self._postprocessors:
            return graph

        pp_context = self._build_pp_context(url, response, existing_web_page_id)
        if not pp_context.account_key:
            raise RuntimeError(
                "Postprocessor runtime requires an API key. Configure one via profile "
                "'api_key', WORDLIFT_KEY, or WORDLIFT_API_KEY."
            )

        for processor in self._postprocessors:
            graph = processor.run(graph, pp_context)
            logger.info("Applied postprocessor '%s' for %s", processor.name, url)
        return graph

    def _build_pp_context(
        self,
        url: str,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
    ) -> PostprocessorContext:
        dataset_uri = str(getattr(self.context.account, "dataset_uri", "")).rstrip("/")
        ids = IdAllocator(dataset_uri) if dataset_uri else None
        profile_payload = asdict(self.profile)
        profile_settings = dict(profile_payload.get("settings", {}) or {})
        profile_settings.setdefault("api_url", "https://api.wordlift.io")
        profile_payload["settings"] = profile_settings
        return PostprocessorContext(
            profile_name=self.profile.name,
            profile=profile_payload,
            url=url,
            account=self.context.account,
            account_key=self._resolve_postprocessor_account_key(),
            exports=self._template_exports or {},
            response=response,
            existing_web_page_id=existing_web_page_id,
            ids=ids,
        )

    def _resolve_postprocessor_account_key(self) -> str | None:
        profile_key = self._clean_key(self.profile.api_key)
        if profile_key:
            return profile_key

        client_config = getattr(self.context, "client_configuration", None)
        if client_config is not None:
            api_key_map = getattr(client_config, "api_key", None)
            if isinstance(api_key_map, dict):
                runtime_key = self._clean_key(api_key_map.get("ApiKey"))
                if runtime_key:
                    return runtime_key

        provider = getattr(self.context, "configuration_provider", None)
        if provider is not None:
            for name in ("WORDLIFT_KEY", "WORDLIFT_API_KEY"):
                try:
                    key = self._clean_key(provider.get_value(name))
                except Exception:
                    key = None
                if key:
                    return key

        for name in ("WORDLIFT_KEY", "WORDLIFT_API_KEY"):
            key = self._clean_key(os.getenv(name))
            if key:
                return key

        return None

    @staticmethod
    def _clean_key(value: Any) -> str | None:
        if value is None:
            return None
        key = str(value).strip()
        return key or None

    def _write_debug_graph(self, graph: Graph, url: str) -> None:
        assert self.debug_dir is not None
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = hashlib.sha256(url.encode("utf-8")).hexdigest()
        debug_file = self.debug_dir / f"{safe_name}.ttl"
        graph.serialize(destination=debug_file, format="turtle")

    def _write_debug_source_documents(
        self, url: str, html: str, xhtml: str | None
    ) -> None:
        assert self.debug_dir is not None
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = hashlib.sha256(url.encode("utf-8")).hexdigest()
        html_file = self.debug_dir / f"{safe_name}.html"
        html_file.write_text(html, encoding="utf-8")
        if xhtml:
            xhtml_file = self.debug_dir / f"{safe_name}.xhtml"
            xhtml_file.write_text(xhtml, encoding="utf-8")

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

    def _set_source(self, graph: Graph, existing_web_page_id: str | None) -> None:
        del existing_web_page_id
        for subject in self._first_level_subjects(graph):
            graph.set((subject, SEOVOC_SOURCE, Literal("web-page-import")))

    def _set_existing_import_hash(self, graph: Graph, import_hash: str | None) -> None:
        if self._import_hash_mode == "off":
            return
        if not import_hash:
            return
        subjects = {
            subject for subject in graph.subjects() if isinstance(subject, URIRef)
        }
        for subject in subjects:
            graph.set((subject, SEOVOC_IMPORT_HASH, Literal(import_hash)))

    def _first_level_subjects(self, graph: Graph) -> set[URIRef]:
        subjects = {
            subject for subject in graph.subjects() if isinstance(subject, URIRef)
        }
        dataset_uri = str(
            getattr(self.context.account, "dataset_uri", "") or ""
        ).rstrip("/")
        if dataset_uri:
            first_level_by_id = {
                subject
                for subject in subjects
                if str(subject).startswith(f"{dataset_uri}/")
                and len(
                    [
                        part
                        for part in str(subject)[len(dataset_uri) + 1 :].split("/")
                        if part
                    ]
                )
                == 2
            }
            if first_level_by_id:
                return first_level_by_id

        referenced = {
            obj
            for _, _, obj in graph.triples((None, None, None))
            if isinstance(obj, URIRef) and obj in subjects
        }
        first_level = subjects - referenced
        return first_level or subjects

    def _mapping_response(
        self,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
    ) -> Any:
        if not existing_web_page_id:
            return response
        # Materialization runtime token __ID__ resolves from response.id.
        return SimpleNamespace(
            id=existing_web_page_id,
            web_page=response.web_page,
        )

    def _validate_graph_if_enabled(
        self, graph: Graph, url: str
    ) -> dict[str, Any] | None:
        if self._shacl_mode == "off":
            return None
        result = self._validate_graph(graph)
        summary = self._summarize_validation(result)
        self._kpi.record_validation(
            passed=summary["pass"],
            warning_count=summary["warnings"]["count"],
            error_count=summary["errors"]["count"],
            warning_sources=summary["warnings"]["sources"],
            error_sources=summary["errors"]["sources"],
        )
        logger.info(
            "SHACL validation for %s: pass=%s warnings=%s errors=%s",
            url,
            summary["pass"],
            summary["warnings"]["count"],
            summary["errors"]["count"],
        )
        return summary

    def _validate_graph(self, graph: Graph) -> ValidationResult:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ttl", delete=False) as f:
            tmp = Path(f.name)
        try:
            graph.serialize(destination=tmp, format="turtle")
            return validate_file(
                str(tmp),
                shape_specs=self._shacl_shape_specs
                if self._shacl_shape_specs
                else None,
            )
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                logger.debug("Failed to remove temporary SHACL graph file: %s", tmp)

    def _summarize_validation(self, result: ValidationResult) -> dict[str, Any]:
        sh = URIRef("http://www.w3.org/ns/shacl#")
        sh_warning = URIRef(f"{sh}Warning")
        sh_violation = URIRef(f"{sh}Violation")
        sh_source_shape = URIRef(f"{sh}sourceShape")

        warning_sources: dict[str, int] = {}
        error_sources: dict[str, int] = {}
        warning_count = 0
        error_count = 0

        for report_node in result.report_graph.subjects(
            URIRef(f"{sh}resultSeverity"), sh_warning
        ):
            warning_count += 1
            shape = next(
                result.report_graph.objects(report_node, sh_source_shape), None
            )
            label = result.shape_source_map.get(shape, "unknown")
            warning_sources[str(label)] = warning_sources.get(str(label), 0) + 1

        for report_node in result.report_graph.subjects(
            URIRef(f"{sh}resultSeverity"), sh_violation
        ):
            error_count += 1
            shape = next(
                result.report_graph.objects(report_node, sh_source_shape), None
            )
            label = result.shape_source_map.get(shape, "unknown")
            error_sources[str(label)] = error_sources.get(str(label), 0) + 1

        return {
            "total": 1,
            "pass": bool(result.conforms),
            "fail": not bool(result.conforms),
            "warnings": {
                "count": warning_count,
                "sources": dict(
                    sorted(warning_sources.items(), key=lambda item: item[0])
                ),
            },
            "errors": {
                "count": error_count,
                "sources": dict(
                    sorted(error_sources.items(), key=lambda item: item[0])
                ),
            },
        }

    def _emit_progress(self, payload: dict[str, Any]) -> None:
        if not callable(self._on_progress):
            return
        try:
            self._on_progress(payload)
        except Exception:
            logger.warning("Failed to emit kg_build progress payload.", exc_info=True)

    def _resolve_list_setting(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, (list, tuple)):
            specs: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    specs.append(text)
            return specs
        return [str(value).strip()] if str(value).strip() else []

    def _resolve_validation_mode(self, value: Any) -> str:
        if value is None:
            return "warn"
        mode = str(value).strip().lower()
        if mode == "strict":
            logger.warning(
                "Deprecated SHACL validation mode 'strict' detected; using 'fail'."
            )
            return "fail"
        if mode in {"off", "warn", "fail"}:
            return mode
        logger.warning("Unsupported SHACL validation mode '%s'; using 'warn'.", mode)
        return "warn"

    def _resolve_import_hash_mode(self, value: Any) -> str:
        if value is None:
            return "on"
        mode = str(value).strip().lower()
        if mode in {"on", "write", "off"}:
            return mode
        logger.warning("Unsupported import hash mode '%s'; using 'on'.", mode)
        return "on"

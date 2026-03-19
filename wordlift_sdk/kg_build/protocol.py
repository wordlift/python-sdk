from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
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
from wordlift_sdk.validation.shacl import resolve_shape_specs
from wordlift_sdk.validation.shacl_validation_service import (
    ShaclValidationService,
    ValidationMode,
    ValidationOutcome,
)

from .config import ProfileDefinition
from .entity_patcher import EntityPatcher
from .id_postprocessor import CanonicalIdsPostprocessor
from .kpi import KgBuildKpiCollector
from .postprocessor_service import PostprocessorService
from .rml_mapping import MappingResult, RmlMappingService
from .templates import JinjaRdfTemplateReifier, TemplateTextRenderer
from wordlift_sdk.structured_data.engine import init_morph_kgc_pool

logger = logging.getLogger(__name__)
SEOVOC_SOURCE = URIRef("https://w3id.org/seovoc/source")
SEOVOC_IMPORT_HASH = URIRef("https://w3id.org/seovoc/importHash")


def _path_contains_part(path: str, part: str) -> bool:
    return part in Path(path).parts


def _setting(settings: dict, name: str, fallback: str, default: Any) -> Any:
    """Read a profile setting by snake_case name, falling back to UPPER_CASE, then default."""
    v = settings.get(name)
    if v is None:
        v = settings.get(fallback)
    return default if v is None else v


def _resolve_postprocessor_runtime(settings: dict[str, Any]) -> str:
    return str(
        _setting(
            settings, "postprocessor_runtime", "POSTPROCESSOR_RUNTIME", "persistent"
        )
    )


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

        settings = dict(self.profile.settings)
        canonical_id_strategy = (
            str(
                _setting(
                    settings, "canonical_id_strategy", "CANONICAL_ID_STRATEGY", "legacy"
                )
            )
            .strip()
            .lower()
        )
        self._core_ids = CanonicalIdsPostprocessor(strategy=canonical_id_strategy)
        _postprocessor_runtime = _resolve_postprocessor_runtime(settings)
        logger.info(
            "Resolved postprocessor runtime for profile '%s': %s (origin=%s)",
            self.profile.name,
            _postprocessor_runtime,
            self.profile.origins.get("postprocessor_runtime", "default"),
        )
        _pool_size = int(_setting(settings, "concurrency", "CONCURRENCY", 4))
        _pp_pool_size = int(
            _setting(
                settings,
                "postprocessor_pool_size",
                "POSTPROCESSOR_POOL_SIZE",
                _pool_size,
            )
        )
        logger.info(
            "Postprocessor pool size for profile '%s': %d (concurrency=%d)",
            self.profile.name,
            _pp_pool_size,
            _pool_size,
        )
        self._postprocessor_service = PostprocessorService(
            root_dir=self.root_dir,
            profile=self.profile,
            context=context,
            pool_size=_pp_pool_size,
            runtime=_postprocessor_runtime,
        )
        _mapping_pool_size = int(
            _setting(
                settings, "mapping_pool_size", "MAPPING_POOL_SIZE", os.cpu_count() or 4
            )
        )
        logger.info(
            "Mapping pool size for profile '%s': %d",
            self.profile.name,
            _mapping_pool_size,
        )
        init_morph_kgc_pool(_mapping_pool_size)
        # Wraps apply_mapping calls so they run in a thread rather than blocking
        # the asyncio event loop. The thread itself blocks on the morph_kgc
        # ProcessPoolExecutor slot, leaving the event loop free for I/O.
        self._mapping_executor = ThreadPoolExecutor(
            max_workers=_pool_size, thread_name_prefix="worai_ml"
        )
        shacl_mode = self._resolve_validation_mode(
            _setting(settings, "shacl_validate_mode", "SHACL_VALIDATE_MODE", "warn")
        )
        shacl_builtin_shapes = self._resolve_list_setting(
            _setting(settings, "shacl_builtin_shapes", "SHACL_BUILTIN_SHAPES", None)
        )
        shacl_exclude_builtin_shapes = self._resolve_list_setting(
            _setting(
                settings,
                "shacl_exclude_builtin_shapes",
                "SHACL_EXCLUDE_BUILTIN_SHAPES",
                None,
            )
        )
        shacl_extra_shapes = self._resolve_list_setting(
            _setting(settings, "shacl_extra_shapes", "SHACL_EXTRA_SHAPES", None)
        )
        self._shacl_shape_specs = resolve_shape_specs(
            builtin_shapes=shacl_builtin_shapes or None,
            exclude_builtin_shapes=shacl_exclude_builtin_shapes or None,
            extra_shapes=shacl_extra_shapes or None,
        )
        _shacl_pool_size = int(
            _setting(
                settings, "shacl_pool_size", "SHACL_POOL_SIZE", max(2, _pool_size // 2)
            )
        )
        self._shacl_validator = ShaclValidationService(
            shape_specs=self._shacl_shape_specs or None,
            mode=shacl_mode,
            pool_size=_shacl_pool_size,
        )
        self._import_hash_mode = self._resolve_import_hash_mode(
            _setting(settings, "import_hash_mode", "IMPORT_HASH_MODE", "on")
        )
        self._kpi = KgBuildKpiCollector(
            dataset_uri=getattr(self.context.account, "dataset_uri", None),
            validation_enabled=self._shacl_validator.mode != ValidationMode.OFF,
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

        # apply_mapping has no awaits — all work is synchronous (morph_kgc).
        # Run it in a thread so the event loop stays free for I/O while the
        # thread waits for its morph_kgc subprocess slot to become available.
        _timing: dict[str, int] = {}

        def _run_mapping() -> Graph | None:
            mapping: MappingResult = asyncio.run(
                self.rml_service.apply_mapping(
                    html=response.web_page.html,
                    url=url,
                    mapping_file_path=mapping_path,
                    mapping_content=rendered_mapping,
                    response=mapping_response,
                    debug_output=debug_output,
                )
            )
            _timing["mapping_wait_ms"] = mapping.queue_wait_ms
            _timing["mapping_ms"] = mapping.mapping_ms
            return mapping.graph

        _loop = asyncio.get_event_loop()
        graph = await _loop.run_in_executor(self._mapping_executor, _run_mapping)
        _t_mapping = _timing.get("mapping_ms", 0)
        _t_mapping_wait = _timing.get("mapping_wait_ms", 0)
        if not graph or len(graph) == 0:
            logger.warning("No triples produced for %s", url)
            return

        if existing_web_page_id:
            self._reconcile_root_id(graph, existing_web_page_id)
        pp_result = await self._postprocessor_service.apply(
            graph, url, response, existing_web_page_id, self._template_exports or {}
        )
        graph = pp_result.graph
        # Canonical IDs must run after custom postprocessors so any nodes minted
        # by local logic are normalized before graph sync patching.
        graph = self._core_ids.process_graph(
            graph,
            self._postprocessor_service.build_context(
                url, response, existing_web_page_id, self._template_exports or {}
            ),
        )
        self._set_source(graph, existing_web_page_id)
        self._set_existing_import_hash(graph, existing_import_hash)

        if self.debug_dir:
            xhtml = (debug_output or {}).get("xhtml")
            self._write_debug_source_documents(
                url=url, html=response.web_page.html, xhtml=xhtml
            )
            self._write_debug_graph(graph, url)

        outcome: ValidationOutcome | None = await self._shacl_validator.validate(graph)
        if outcome is not None:
            logger.info(
                "SHACL validation for %s: pass=%s warnings=%d errors=%d",
                url,
                outcome.passed,
                outcome.warning_count,
                outcome.error_count,
            )
            self._kpi.record_validation(
                passed=outcome.passed,
                warning_count=outcome.warning_count,
                error_count=outcome.error_count,
                warning_sources=outcome.warning_sources,
                error_sources=outcome.error_sources,
            )
        _t_validation_wait = outcome.queue_wait_ms if outcome else 0
        _t_validation_actual = outcome.validation_ms if outcome else 0
        graph_metrics = self._kpi.graph_metrics(graph)
        self._emit_progress(
            {
                "kind": "graph",
                "profile": self.profile.name,
                "url": url,
                "graph": graph_metrics,
                "validation": outcome.to_dict() if outcome else None,
            }
        )
        self._kpi.record_graph(graph)
        if (
            outcome is not None
            and self._shacl_validator.mode == ValidationMode.FAIL
            and outcome.failed
        ):
            raise RuntimeError(f"SHACL validation failed for {url} in fail mode.")
        await self._write_graph(graph)
        logger.info(
            "Wrote %s triples for %s [mapping_wait=%dms mapping=%dms postprocessor_wait=%dms postprocessors=%dms validation_wait=%dms validation=%dms]",
            len(graph),
            url,
            _t_mapping_wait,
            _t_mapping,
            pp_result.queue_wait_ms,
            pp_result.postprocessors_ms,
            _t_validation_wait,
            _t_validation_actual,
        )

    def close(self) -> None:
        self._postprocessor_service.close()
        self._mapping_executor.shutdown(wait=False)
        self._shacl_validator.close()

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
                outcome = await self._shacl_validator.validate(self._template_graph)
                if outcome is not None:
                    logger.info(
                        "SHACL validation for static_templates: pass=%s warnings=%d errors=%d",
                        outcome.passed,
                        outcome.warning_count,
                        outcome.error_count,
                    )
                    self._kpi.record_validation(
                        passed=outcome.passed,
                        warning_count=outcome.warning_count,
                        error_count=outcome.error_count,
                        warning_sources=outcome.warning_sources,
                        error_sources=outcome.error_sources,
                    )
                self._emit_progress(
                    {
                        "kind": "static_templates",
                        "profile": self.profile.name,
                        "graph": self._kpi.graph_metrics(self._template_graph),
                        "validation": outcome.to_dict() if outcome else None,
                    }
                )
                self._kpi.record_graph(self._template_graph)
                if (
                    outcome is not None
                    and self._shacl_validator.mode == ValidationMode.FAIL
                    and outcome.failed
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

    def _resolve_validation_mode(self, value: Any) -> ValidationMode:
        if value is None:
            return ValidationMode.WARN
        mode = str(value).strip().lower()
        if mode == "strict":
            logger.warning(
                "Deprecated SHACL validation mode 'strict' detected; using 'fail'."
            )
            return ValidationMode.FAIL
        try:
            return ValidationMode(mode)
        except ValueError:
            logger.warning(
                "Unsupported SHACL validation mode '%s'; using 'warn'.", mode
            )
            return ValidationMode.WARN

    def _resolve_import_hash_mode(self, value: Any) -> str:
        if value is None:
            return "on"
        mode = str(value).strip().lower()
        if mode in {"on", "write", "off"}:
            return mode
        logger.warning("Unsupported import hash mode '%s'; using 'on'.", mode)
        return "on"

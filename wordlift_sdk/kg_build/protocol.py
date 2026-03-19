from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jinja2 import UndefinedError
from rdflib import Graph, URIRef
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
from .graph_annotation import ImportAnnotationPostprocessor
from .graph_utils import first_level_subjects
from .id_allocator import IdAllocator
from .id_postprocessor import CanonicalIdsPostprocessor, RootIdReconcilerPostprocessor
from .kpi import KgBuildKpiCollector
from .postprocessor_service import PostprocessorService
from .postprocessors import (
    LoadedPostprocessor,
    PostprocessorContext,
    PostprocessorResult,
    load_postprocessors_for_profile,
)
from .rml_mapping import MappingResult, RmlMappingService
from .templates import JinjaRdfTemplateReifier, TemplateTextRenderer
from wordlift_sdk.structured_data.engine import init_morph_kgc_pool

logger = logging.getLogger(__name__)


def _path_contains_part(path: str, part: str) -> bool:
    return part in Path(path).parts


def _clean_key(value: Any) -> str | None:
    key = str(value).strip() if value is not None else ""
    return key or None


def _resolve_account_key(profile: Any, context: Any) -> str | None:
    if key := _clean_key(getattr(profile, "api_key", None)):
        return key
    api_key_map = getattr(
        getattr(context, "client_configuration", None), "api_key", None
    )
    if isinstance(api_key_map, dict):
        if key := _clean_key(api_key_map.get("ApiKey")):
            return key
    provider = getattr(context, "configuration_provider", None)
    if provider is not None:
        for name in ("WORDLIFT_KEY", "WORDLIFT_API_KEY"):
            try:
                if key := _clean_key(provider.get_value(name)):
                    return key
            except Exception:
                pass
    for name in ("WORDLIFT_KEY", "WORDLIFT_API_KEY"):
        if key := _clean_key(os.getenv(name)):
            return key
    return None


def _resolve_list_setting(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [text for item in value if (text := str(item).strip())]
    return [str(value).strip()] if str(value).strip() else []


def _resolve_validation_mode(value: Any) -> ValidationMode:
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
        logger.warning("Unsupported SHACL validation mode '%s'; using 'warn'.", mode)
        return ValidationMode.WARN


def _resolve_import_hash_mode(value: Any) -> str:
    if value is None:
        return "on"
    mode = str(value).strip().lower()
    if mode in {"on", "write", "off"}:
        return mode
    logger.warning("Unsupported import hash mode '%s'; using 'on'.", mode)
    return "on"


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

        settings = dict(self.profile.settings)
        _pool_size = int(_setting(settings, "concurrency", "CONCURRENCY", 4))
        self._init_postprocessor_service(settings, context, _pool_size)
        self._init_mapping_service(settings, context, _pool_size)
        self._init_shacl_validator(settings, _pool_size)
        self._init_graph_writer(settings, context)
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

    def _init_postprocessor_service(
        self, settings: dict, context: Context, pool_size: int
    ) -> None:
        canonical_id_strategy = (
            str(
                _setting(
                    settings, "canonical_id_strategy", "CANONICAL_ID_STRATEGY", "legacy"
                )
            )
            .strip()
            .lower()
        )
        core_ids = CanonicalIdsPostprocessor(strategy=canonical_id_strategy)
        runtime = _resolve_postprocessor_runtime(settings)
        logger.info(
            "Resolved postprocessor runtime for profile '%s': %s (origin=%s)",
            self.profile.name,
            runtime,
            self.profile.origins.get("postprocessor_runtime", "default"),
        )
        pp_pool_size = int(
            _setting(
                settings,
                "postprocessor_pool_size",
                "POSTPROCESSOR_POOL_SIZE",
                pool_size,
            )
        )
        logger.info(
            "Postprocessor pool size for profile '%s': %d (concurrency=%d)",
            self.profile.name,
            pp_pool_size,
            pool_size,
        )
        account_key = _resolve_account_key(self.profile, context)
        root_dir = self.root_dir
        profile = self.profile

        def _postprocessors_factory() -> list[LoadedPostprocessor]:
            leading = [
                LoadedPostprocessor(
                    name="root_id_reconciler",
                    handler=RootIdReconcilerPostprocessor(),
                )
            ]
            custom = load_postprocessors_for_profile(
                root_dir=root_dir,
                profile_name=profile.name,
                runtime=runtime,
            )
            trailing = [
                LoadedPostprocessor(name="canonical_ids", handler=core_ids),
                LoadedPostprocessor(
                    name="import_annotation",
                    handler=ImportAnnotationPostprocessor(),
                ),
            ]
            return leading + custom + trailing

        self._account_key = account_key
        self._postprocessor_service = PostprocessorService(
            postprocessors_factory=_postprocessors_factory,
            pool_size=pp_pool_size,
        )

    def _init_mapping_service(
        self, settings: dict, context: Context, pool_size: int
    ) -> None:
        self.templates_dir = self._resolve_path(self.profile.templates_dir)
        self.mappings_dir = self._resolve_path(self.profile.mappings_dir)
        self._template_dirs = self._resolve_overlay_paths(
            self.profile.template_overlay_dirs or (self.profile.templates_dir,)
        )
        self._mapping_dirs = self._resolve_overlay_paths(
            self.profile.mapping_overlay_dirs or (self.profile.mappings_dir,)
        )
        self.template_reifier = JinjaRdfTemplateReifier(self._template_dirs)
        self.text_renderer = TemplateTextRenderer()
        self._template_graph: Graph | None = None
        self._template_exports: dict[str, Any] | None = None
        self._mapping_cache: dict[Path, str] = {}
        self._static_templates_patched = False
        self._static_templates_lock = asyncio.Lock()
        self.rml_service = RmlMappingService(context)
        mapping_pool_size = int(
            _setting(
                settings, "mapping_pool_size", "MAPPING_POOL_SIZE", os.cpu_count() or 4
            )
        )
        logger.info(
            "Mapping pool size for profile '%s': %d",
            self.profile.name,
            mapping_pool_size,
        )
        init_morph_kgc_pool(mapping_pool_size)
        # Wraps apply_mapping calls so they run in a thread rather than blocking
        # the asyncio event loop. The thread itself blocks on the morph_kgc
        # ProcessPoolExecutor slot, leaving the event loop free for I/O.
        self._mapping_executor = ThreadPoolExecutor(
            max_workers=pool_size, thread_name_prefix="worai_ml"
        )

    def _init_shacl_validator(self, settings: dict, pool_size: int) -> None:
        mode = _resolve_validation_mode(
            _setting(settings, "shacl_validate_mode", "SHACL_VALIDATE_MODE", "warn")
        )
        builtin_shapes = _resolve_list_setting(
            _setting(settings, "shacl_builtin_shapes", "SHACL_BUILTIN_SHAPES", None)
        )
        exclude_builtin_shapes = _resolve_list_setting(
            _setting(
                settings,
                "shacl_exclude_builtin_shapes",
                "SHACL_EXCLUDE_BUILTIN_SHAPES",
                None,
            )
        )
        extra_shapes = _resolve_list_setting(
            _setting(settings, "shacl_extra_shapes", "SHACL_EXTRA_SHAPES", None)
        )
        shape_specs = resolve_shape_specs(
            builtin_shapes=builtin_shapes or None,
            exclude_builtin_shapes=exclude_builtin_shapes or None,
            extra_shapes=extra_shapes or None,
        )
        shacl_pool_size = int(
            _setting(
                settings, "shacl_pool_size", "SHACL_POOL_SIZE", max(2, pool_size // 2)
            )
        )
        self._shacl_validator = ShaclValidationService(
            shape_specs=shape_specs or None,
            mode=mode,
            pool_size=shacl_pool_size,
        )

    def _init_graph_writer(self, settings: dict, context: Context) -> None:
        self.patcher = EntityPatcher(context)
        self._import_hash_mode = _resolve_import_hash_mode(
            _setting(settings, "import_hash_mode", "IMPORT_HASH_MODE", "on")
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

        debug_output: dict[str, str] | None = {} if self.debug_dir else None
        mapping = await self._run_mapping_stage(
            response, url, existing_web_page_id, debug_output
        )
        if not mapping.graph or len(mapping.graph) == 0:
            logger.warning("No triples produced for %s", url)
            return

        pp_result = await self._run_postprocessing_stage(
            mapping.graph, url, response, existing_web_page_id, existing_import_hash
        )

        if self.debug_dir:
            xhtml = (debug_output or {}).get("xhtml")
            self._write_debug_source_documents(
                url=url, html=response.web_page.html, xhtml=xhtml
            )
            self._write_debug_graph(pp_result.graph, url)

        outcome: ValidationOutcome | None = await self._shacl_validator.validate(
            pp_result.graph
        )
        if outcome is not None:
            logger.info(
                "SHACL validation for %s: pass=%s warnings=%d errors=%d",
                url,
                outcome.passed,
                outcome.warning_count,
                outcome.error_count,
            )
            self._kpi.record_validation(outcome)
        self._kpi.record_graph(pp_result.graph)
        self._emit_progress(
            {
                "kind": "graph",
                "profile": self.profile.name,
                "url": url,
                "graph": self._kpi.graph_metrics(pp_result.graph),
                "validation": outcome.to_dict() if outcome else None,
            }
        )
        if (
            outcome is not None
            and self._shacl_validator.mode == ValidationMode.FAIL
            and outcome.failed
        ):
            raise RuntimeError(f"SHACL validation failed for {url} in fail mode.")
        await self._write_graph(pp_result.graph)
        logger.info(
            "Wrote %s triples for %s [mapping_wait=%dms mapping=%dms postprocessor_wait=%dms postprocessors=%dms validation_wait=%dms validation=%dms]",
            len(pp_result.graph),
            url,
            mapping.queue_wait_ms,
            mapping.mapping_ms,
            pp_result.queue_wait_ms,
            pp_result.postprocessors_ms,
            outcome.queue_wait_ms if outcome else 0,
            outcome.validation_ms if outcome else 0,
        )

    def close(self) -> None:
        self._postprocessor_service.close()
        self._mapping_executor.shutdown(wait=False)
        self._shacl_validator.close()

    def get_kpi_summary(self) -> dict[str, object]:
        return self._kpi.summary(self.profile.name)

    @property
    def _dataset_uri(self) -> str:
        return str(getattr(self.context.account, "dataset_uri", "") or "").rstrip("/")

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    async def _run_mapping_stage(
        self,
        response: WebPageScrapeResponse,
        url: str,
        existing_web_page_id: str | None,
        debug_output: dict[str, str] | None,
    ) -> MappingResult:
        mapping_path = self._resolve_mapping_path(url)
        rendered_mapping = self._get_mapping_content(mapping_path)
        mapping_response = self._mapping_response(response, existing_web_page_id)

        def _run() -> MappingResult:
            # apply_mapping has no awaits — all work is synchronous (morph_kgc).
            # Run in a thread so the event loop stays free for I/O while the
            # thread waits for its morph_kgc subprocess slot.
            return asyncio.run(
                self.rml_service.apply_mapping(
                    html=response.web_page.html,
                    url=url,
                    mapping_file_path=mapping_path,
                    mapping_content=rendered_mapping,
                    response=mapping_response,
                    debug_output=debug_output,
                )
            )

        return await asyncio.get_event_loop().run_in_executor(
            self._mapping_executor, _run
        )

    async def _run_postprocessing_stage(
        self,
        graph: Graph,
        url: str,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
        existing_import_hash: str | None,
    ) -> PostprocessorResult:
        context = self._build_pp_context(
            url, response, existing_web_page_id, existing_import_hash
        )
        return await self._postprocessor_service.apply(graph, context)

    def _build_pp_context(
        self,
        url: str,
        response: WebPageScrapeResponse,
        existing_web_page_id: str | None,
        existing_import_hash: str | None,
    ) -> PostprocessorContext:
        dataset_uri = self._dataset_uri
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
            account_key=self._account_key,
            exports=self._template_exports or {},
            response=response,
            existing_web_page_id=existing_web_page_id,
            existing_import_hash=existing_import_hash,
            import_hash_mode=self._import_hash_mode,
            ids=ids,
        )

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
                    self._kpi.record_validation(outcome)
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

        dataset_uri = self._dataset_uri
        if not dataset_uri:
            raise RuntimeError("Dataset URI not available on context.account.")

        base_context = {
            "account": self.context.account,
            "dataset_uri": dataset_uri,
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

        dataset_uri = self._dataset_uri
        if not dataset_uri:
            raise RuntimeError("Dataset URI not available on context.account.")

        self._ensure_templates_loaded()

        context = {
            "account": self.context.account,
            "dataset_uri": dataset_uri,
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
        dataset_uri = self._dataset_uri
        if not dataset_uri:
            return False

        subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(dataset_uri)
        }
        if not subjects:
            return False

        page_subjects = {
            subject
            for subject in first_level_subjects(graph, dataset_uri)
            if subject in subjects
        }
        if not page_subjects:
            return False

        if self._import_hash_mode == "off":
            return True

        representative = next(iter(page_subjects))
        existing_hash = self.patcher._existing_import_hash(representative, graph)
        import_hash = self.patcher._compute_import_hash(
            representative, graph, dataset_uri
        )
        for subject in page_subjects:
            self.patcher._set_import_hash(subject, graph, import_hash)

        return not (
            self._import_hash_mode == "on"
            and existing_hash
            and existing_hash == import_hash
        )

    def _write_debug_graph(self, graph: Graph, url: str) -> None:
        assert self.debug_dir is not None
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._url_hash(url)
        debug_file = self.debug_dir / f"{safe_name}.ttl"
        graph.serialize(destination=debug_file, format="turtle")

    def _write_debug_source_documents(
        self, url: str, html: str, xhtml: str | None
    ) -> None:
        assert self.debug_dir is not None
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._url_hash(url)
        html_file = self.debug_dir / f"{safe_name}.html"
        html_file.write_text(html, encoding="utf-8")
        if xhtml:
            xhtml_file = self.debug_dir / f"{safe_name}.xhtml"
            xhtml_file.write_text(xhtml, encoding="utf-8")

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

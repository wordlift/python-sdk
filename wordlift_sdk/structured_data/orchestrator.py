"""Orchestration for structured data workflows."""

from __future__ import annotations

import json
from typing import Callable

from wordlift_sdk.structured_data.engine import (
    StructuredDataOptions,
    StructuredDataResult,
)
from wordlift_sdk.structured_data.constants import DEFAULT_BASE_URL
from wordlift_sdk.structured_data.structured_data_engine import StructuredDataEngine
from wordlift_sdk.structured_data.yarrrml_pipeline import YarrrmlPipeline

from .agent import AgentGenerator
from .batch import BatchGenerator
from .debug import echo_debug
from .io import default_output_paths, write_output
from .inputs import filter_urls, resolve_input_urls
from .models import CreateRequest, GenerateRequest
from .rendering import RenderPipeline
from .validation import ValidationService


class CreateWorkflow:
    """Workflow for generating structured data from a single URL."""

    def __init__(
        self,
        agent: AgentGenerator | None = None,
        renderer: RenderPipeline | None = None,
        validator: ValidationService | None = None,
        engine: StructuredDataEngine | None = None,
    ) -> None:
        self._agent = agent or AgentGenerator()
        self._renderer = renderer
        self._validator = validator or ValidationService()
        self._engine = engine or StructuredDataEngine()
        self._yarrrml = YarrrmlPipeline()

    def run(
        self, request: CreateRequest, log: Callable[[str], None]
    ) -> StructuredDataResult:
        if not request.api_key:
            raise RuntimeError(
                "WORDLIFT_KEY is required (or set wordlift.api_key in config)."
            )
        base_url = request.base_url or DEFAULT_BASE_URL
        dataset_uri = self._engine.get_dataset_uri(request.api_key, base_url=base_url)

        renderer = self._renderer or RenderPipeline(
            headed=request.headed,
            timeout_ms=request.timeout_ms,
            wait_until=request.wait_until,
            max_xhtml_chars=request.max_xhtml_chars,
            max_text_node_chars=request.max_text_node_chars,
        )

        rendered, cleaned_xhtml = renderer.render(request.url, log)

        options = StructuredDataOptions(
            url=request.url,
            target_type=request.target_type,
            dataset_uri=dataset_uri,
            headless=not request.headed,
            timeout_ms=request.timeout_ms,
            wait_until=request.wait_until,
            max_retries=request.max_retries,
            max_xhtml_chars=request.max_xhtml_chars,
            max_text_node_chars=request.max_text_node_chars,
            max_nesting_depth=request.max_nesting_depth,
            verbose=request.verbose,
        )

        workdir = request.output_dir / ".structured-data"
        debug_path = workdir / "agent_debug.json"
        try:
            log("Generating YARRRML mapping and JSON-LD...")
            yarrml, jsonld = self._agent.generate(
                options.url,
                rendered.html,
                rendered.xhtml,
                cleaned_xhtml,
                request.api_key,
                options.dataset_uri,
                options.target_type,
                workdir,
                debug=request.debug,
                max_retries=options.max_retries,
                max_nesting_depth=options.max_nesting_depth,
                quality_check=request.quality_check,
                log=log,
            )
        except Exception:
            if request.debug:
                echo_debug(debug_path, log)
            raise
        if request.debug:
            echo_debug(debug_path, log)

        jsonld_path = request.jsonld_path
        yarrml_path = request.yarrml_path
        if jsonld_path is None or yarrml_path is None:
            jsonld_path, yarrml_path = default_output_paths(
                request.output_dir, request.base_name
            )

        write_output(jsonld_path, json.dumps(jsonld, indent=2))
        yarrml = self._yarrrml.make_reusable_yarrrml(yarrml, request.url)
        write_output(yarrml_path, yarrml)

        if request.verbose:
            mapping_validation_path = workdir / "mapping.validation.json"
            if mapping_validation_path.exists():
                try:
                    validation_payload = json.loads(mapping_validation_path.read_text())
                except Exception:
                    validation_payload = {}
                for warning in validation_payload.get("warnings", []):
                    if "reviewRating dropped" in warning:
                        log(warning)

        if request.validate:
            log("Validating JSON-LD output...")
            report_text = self._validator.validate(
                jsonld_path, request.target_type, workdir
            )
            log(report_text)

        return StructuredDataResult(
            jsonld=jsonld,
            yarrml=yarrml,
            jsonld_filename=str(jsonld_path),
            yarrml_filename=str(yarrml_path),
        )


class GenerateWorkflow:
    """Workflow for generating structured data in batch from YARRRML."""

    def __init__(self, engine: StructuredDataEngine | None = None) -> None:
        self._engine = engine or StructuredDataEngine()

    def run(
        self, request: GenerateRequest, log: Callable[[str], None]
    ) -> dict[str, object]:
        base_url = request.base_url or DEFAULT_BASE_URL
        dataset_uri = (
            self._engine.get_dataset_uri(request.api_key, base_url=base_url)
            if request.api_key
            else None
        )
        if not dataset_uri:
            raise RuntimeError(
                "WORDLIFT_KEY is required (or set wordlift.api_key in config)."
            )
        if not request.yarrrml_path.exists():
            raise RuntimeError(f"YARRRML file not found: {request.yarrrml_path}")
        yarrrml = request.yarrrml_path.read_text()

        urls = resolve_input_urls(request.input_value)
        urls = filter_urls(urls, request.regex, request.max_pages)

        batch = BatchGenerator(
            output_dir=request.output_dir,
            output_format=request.output_format,
            concurrency=request.concurrency,
            headed=request.headed,
            timeout_ms=request.timeout_ms,
            wait_until=request.wait_until,
            max_xhtml_chars=request.max_xhtml_chars,
            max_text_node_chars=request.max_text_node_chars,
            dataset_uri=dataset_uri,
            verbose=request.verbose,
        )
        summary = batch.generate(urls, yarrrml, log)
        summary["input"] = request.input_value
        return summary


def resolve_api_key_from_context(
    ctx_config: object | None, env_key: str = "WORDLIFT_KEY"
) -> str | None:
    if ctx_config is not None:
        try:
            value = ctx_config.get("wordlift.api_key")
            if value:
                return value
        except Exception:
            return None
    import os

    return os.environ.get(env_key)

from pathlib import Path

import pytest

import wordlift_sdk.structured_data.orchestrator as orchestrator_module
import wordlift_sdk.structured_data.rendering as rendering_module
from wordlift_sdk.structured_data.engine import StructuredDataResult
from wordlift_sdk.structured_data.models import CreateRequest, GenerateRequest
from wordlift_sdk.structured_data.orchestrator import (
    CreateWorkflow,
    GenerateWorkflow,
    resolve_api_key_from_context,
)


class _Rendered:
    def __init__(self, html="<html></html>", xhtml="<html/>"):
        self.html = html
        self.xhtml = xhtml


class _Renderer:
    def render(self, url, log):
        log(f"render:{url}")
        return _Rendered(), "cleaned"


class _Agent:
    def generate(self, *args, **kwargs):
        return "mappings: {}", {"@context": "https://schema.org"}


class _Engine:
    def __init__(self, dataset_uri="https://data.example.org/dataset"):
        self.dataset_uri = dataset_uri

    def get_dataset_uri(self, api_key, base_url=None, ssl_ca_cert=None):
        return self.dataset_uri


class _Yarrrml:
    def make_reusable_yarrrml(self, yarrml, url):
        return f"{yarrml}\n# url={url}"


class _Validator:
    def validate(self, jsonld_path, target_type, workdir):
        return "validation-ok"


def _create_request(tmp_path: Path, *, validate=False, verbose=False, api_key="k"):
    return CreateRequest(
        url="https://example.org/page",
        target_type="Article",
        output_dir=tmp_path,
        base_name="page",
        jsonld_path=None,
        yarrml_path=None,
        api_key=api_key,
        base_url=None,
        ssl_ca_cert=None,
        debug=False,
        headed=False,
        timeout_ms=1000,
        max_retries=1,
        quality_check=False,
        max_xhtml_chars=10000,
        max_text_node_chars=200,
        max_nesting_depth=2,
        verbose=verbose,
        validate=validate,
        wait_until="load",
    )


def test_render_pipeline_calls_render_and_clean(monkeypatch):
    calls = {}

    def _render_html(options):
        calls["render_url"] = options.url
        calls["headless"] = options.headless
        return _Rendered(xhtml="<xhtml/>")

    def _clean_xhtml(xhtml, options):
        calls["xhtml"] = xhtml
        calls["max_xhtml_chars"] = options.max_xhtml_chars
        return "cleaned"

    monkeypatch.setattr(rendering_module, "render_html", _render_html)
    monkeypatch.setattr(rendering_module, "clean_xhtml", _clean_xhtml)

    logs = []
    pipeline = rendering_module.RenderPipeline(
        headed=True,
        timeout_ms=1200,
        wait_until="networkidle",
        max_xhtml_chars=5000,
        max_text_node_chars=300,
    )
    rendered, cleaned = pipeline.render("https://example.org", logs.append)

    assert cleaned == "cleaned"
    assert rendered.xhtml == "<xhtml/>"
    assert calls["render_url"] == "https://example.org"
    assert calls["headless"] is False
    assert calls["xhtml"] == "<xhtml/>"
    assert calls["max_xhtml_chars"] == 5000
    assert logs == [
        "Rendering page with Playwright...",
        "Cleaning XHTML for prompt usage...",
    ]


def test_create_workflow_run_writes_outputs_and_validates(tmp_path: Path):
    workflow = CreateWorkflow(
        agent=_Agent(),
        renderer=_Renderer(),
        validator=_Validator(),
        engine=_Engine(),
    )
    workflow._yarrrml = _Yarrrml()

    logs = []
    request = _create_request(tmp_path, validate=True, verbose=True)

    workdir = tmp_path / ".structured-data"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "mapping.validation.json").write_text(
        '{"warnings":["reviewRating dropped: missing value","ignore-me"]}'
    )

    result = workflow.run(request, logs.append)

    assert isinstance(result, StructuredDataResult)
    assert Path(result.jsonld_filename).exists()
    assert Path(result.yarrml_filename).exists()
    assert "# url=https://example.org/page" in Path(result.yarrml_filename).read_text()
    assert "Validating JSON-LD output..." in logs
    assert "validation-ok" in logs
    assert any("reviewRating dropped" in line for line in logs)


def test_create_workflow_requires_api_key(tmp_path: Path):
    workflow = CreateWorkflow(
        agent=_Agent(), renderer=_Renderer(), validator=_Validator(), engine=_Engine()
    )
    request = _create_request(tmp_path, api_key=None)

    with pytest.raises(RuntimeError, match="WORDLIFT_KEY is required"):
        workflow.run(request, lambda *_: None)


def test_generate_workflow_success(monkeypatch, tmp_path: Path):
    yarrml_path = tmp_path / "input.yarrml"
    yarrml_path.write_text("mappings: {}")

    class _Batch:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def generate(self, urls, yarrml, log):
            return {"count": len(urls), "output_format": self.kwargs["output_format"]}

    monkeypatch.setattr(orchestrator_module, "BatchGenerator", _Batch)
    monkeypatch.setattr(
        orchestrator_module, "resolve_input_urls", lambda value: ["u1", "u2"]
    )
    monkeypatch.setattr(
        orchestrator_module, "filter_urls", lambda urls, regex, max_pages: urls[:1]
    )

    request = GenerateRequest(
        input_value="https://example.org/sitemap.xml",
        yarrrml_path=yarrml_path,
        regex=".*",
        output_dir=tmp_path,
        output_format="ttl",
        concurrency="2",
        api_key="k",
        base_url=None,
        ssl_ca_cert=None,
        headed=False,
        timeout_ms=1000,
        wait_until="load",
        max_xhtml_chars=10000,
        max_text_node_chars=200,
        max_pages=10,
        verbose=False,
    )

    summary = orchestrator_module.GenerateWorkflow(engine=_Engine()).run(
        request, lambda *_: None
    )

    assert summary["count"] == 1
    assert summary["output_format"] == "ttl"
    assert summary["input"] == "https://example.org/sitemap.xml"


def test_generate_workflow_errors(tmp_path: Path):
    missing = tmp_path / "missing.yarrml"
    workflow = GenerateWorkflow(engine=_Engine(dataset_uri=None))

    request_missing_key = GenerateRequest(
        input_value="https://example.org",
        yarrrml_path=missing,
        regex=".*",
        output_dir=tmp_path,
        output_format="ttl",
        concurrency="1",
        api_key=None,
        base_url=None,
        ssl_ca_cert=None,
        headed=False,
        timeout_ms=1000,
        wait_until="load",
        max_xhtml_chars=1000,
        max_text_node_chars=100,
        max_pages=None,
        verbose=False,
    )

    with pytest.raises(RuntimeError, match="WORDLIFT_KEY is required"):
        workflow.run(request_missing_key, lambda *_: None)

    request_missing_file = GenerateRequest(
        input_value="https://example.org",
        yarrrml_path=missing,
        regex=".*",
        output_dir=tmp_path,
        output_format="ttl",
        concurrency="1",
        api_key="k",
        base_url=None,
        ssl_ca_cert=None,
        headed=False,
        timeout_ms=1000,
        wait_until="load",
        max_xhtml_chars=1000,
        max_text_node_chars=100,
        max_pages=None,
        verbose=False,
    )

    with pytest.raises(RuntimeError, match="YARRRML file not found"):
        GenerateWorkflow(engine=_Engine()).run(request_missing_file, lambda *_: None)


def test_resolve_api_key_from_context(monkeypatch):
    class _Ctx:
        def get(self, key):
            return "ctx-key"

    assert resolve_api_key_from_context(_Ctx()) == "ctx-key"

    class _BrokenCtx:
        def get(self, key):
            raise RuntimeError("boom")

    monkeypatch.setenv("WORDLIFT_KEY", "env-key")
    assert resolve_api_key_from_context(_BrokenCtx()) is None
    assert resolve_api_key_from_context(None) == "env-key"

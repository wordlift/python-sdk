from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

import wordlift_sdk.structured_data.orchestrator as orchestrator_module
import wordlift_sdk.structured_data.structured_data_engine as structured_data_engine_module
import wordlift_sdk.structured_data.yarrrml_pipeline as yarrrml_pipeline_module

if "wordlift_client" not in sys.modules:
    try:
        import wordlift_client  # noqa: F401
    except Exception:
        _fake_client = types.ModuleType("wordlift_client")

        class _ApiClient:  # noqa: D401 - simple stub
            pass

        class _Configuration:
            def __init__(self, *args, **kwargs) -> None:
                self.api_key = {}

        class _AgentApi:
            def __init__(self, *args, **kwargs) -> None:
                pass

        class _AccountApi:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def get_me(self):
                return types.SimpleNamespace(dataset_uri="urn:dataset")

        _fake_client.ApiClient = _ApiClient
        _fake_client.Configuration = _Configuration
        _fake_client.AgentApi = _AgentApi
        _fake_client.AccountApi = _AccountApi
        sys.modules.setdefault("wordlift_client", _fake_client)

        _models_module = types.ModuleType("wordlift_client.models")
        _ask_module = types.ModuleType("wordlift_client.models.ask_request")

        class _AskRequest:
            def __init__(self, *args, **kwargs) -> None:
                pass

        _ask_module.AskRequest = _AskRequest
        sys.modules.setdefault("wordlift_client.models", _models_module)
        sys.modules.setdefault("wordlift_client.models.ask_request", _ask_module)

try:
    import pyshacl as _pyshacl_real  # noqa: F401
except ImportError:
    _pyshacl = types.ModuleType("pyshacl")

    def _stub_validate(*_args, **_kwargs):
        return None, None, None

    _pyshacl.validate = _stub_validate
    sys.modules["pyshacl"] = _pyshacl

from wordlift_sdk.structured_data import (  # noqa: E402
    CreateRequest,
    CreateWorkflow,
    GenerateRequest,
    GenerateWorkflow,
)
from wordlift_sdk.structured_data.engine import StructuredDataOptions  # noqa: E402
from wordlift_sdk.render.render_options import (  # noqa: E402
    DEFAULT_PLAYWRIGHT_TIMEOUT_MS,
    DEFAULT_PLAYWRIGHT_WAIT_UNTIL,
)


class _FakeRendered:
    def __init__(self) -> None:
        self.html = "<html><body>Hi</body></html>"
        self.xhtml = "<html><body>Hi</body></html>"
        self.status_code = 200


class _FakeRenderer:
    def __init__(self) -> None:
        self.seen = []

    def render(self, url: str, log) -> tuple[object, str]:
        self.seen.append(url)
        return _FakeRendered(), "<html><body>Hi</body></html>"


class _FakeAgent:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "mappings: []", {"@context": "https://schema.org", "@type": "Thing"}


class _FakeValidator:
    def __init__(self) -> None:
        self.calls = []

    def validate(self, jsonld_path: Path, target_type: str, workdir: Path) -> str:
        self.calls.append((jsonld_path, target_type, workdir))
        return "OK"


def test_structured_data_options_use_shared_playwright_defaults() -> None:
    options = StructuredDataOptions(
        url="https://example.com",
        target_type="Thing",
        dataset_uri="urn:dataset",
    )
    assert options.timeout_ms == DEFAULT_PLAYWRIGHT_TIMEOUT_MS
    assert options.wait_until == DEFAULT_PLAYWRIGHT_WAIT_UNTIL


def test_create_workflow_writes_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_get_dataset_uri(
        self, api_key: str, base_url: str | None = None, ssl_ca_cert: str | None = None
    ) -> str:
        return "urn:dataset"

    def _fake_make_reusable_yarrrml(self, yarrrml: str, url: str) -> str:
        return f"# {url}\n{yarrrml}"

    monkeypatch.setattr(
        structured_data_engine_module.StructuredDataEngine,
        "get_dataset_uri",
        _fake_get_dataset_uri,
    )
    monkeypatch.setattr(
        yarrrml_pipeline_module.YarrrmlPipeline,
        "make_reusable_yarrrml",
        _fake_make_reusable_yarrrml,
    )

    agent = _FakeAgent()
    renderer = _FakeRenderer()
    validator = _FakeValidator()

    request = CreateRequest(
        url="https://example.com",
        target_type="Thing",
        output_dir=tmp_path,
        base_name="structured-data",
        jsonld_path=None,
        yarrml_path=None,
        api_key="test-key",
        base_url=None,
        ssl_ca_cert=None,
        debug=False,
        headed=False,
        timeout_ms=1000,
        max_retries=0,
        quality_check=False,
        max_xhtml_chars=1000,
        max_text_node_chars=200,
        max_nesting_depth=1,
        verbose=False,
        validate=True,
        wait_until="load",
    )

    workflow = CreateWorkflow(agent=agent, renderer=renderer, validator=validator)
    result = workflow.run(request, log=lambda *_: None)

    jsonld_path = tmp_path / "structured-data.jsonld"
    yarrml_path = tmp_path / "structured-data.yarrml"
    assert jsonld_path.exists()
    assert yarrml_path.exists()
    assert json.loads(jsonld_path.read_text())["@type"] == "Thing"
    assert result.jsonld_filename == str(jsonld_path)
    assert result.yarrml_filename == str(yarrml_path)
    assert agent.calls
    assert renderer.seen == ["https://example.com"]
    assert validator.calls


def test_generate_workflow_runs_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    yarrrml_path = tmp_path / "mapping.yarrrml"
    yarrrml_path.write_text("mappings: []")

    monkeypatch.setattr(
        orchestrator_module, "resolve_input_urls", lambda value: ["https://example.com"]
    )
    monkeypatch.setattr(
        orchestrator_module, "filter_urls", lambda urls, regex, max_pages: urls
    )
    monkeypatch.setattr(
        structured_data_engine_module.StructuredDataEngine,
        "get_dataset_uri",
        lambda self, api_key, base_url=None, ssl_ca_cert=None: "urn:dataset",
    )

    class _FakeBatch:
        def __init__(self, **_kwargs) -> None:
            pass

        def generate(self, urls, yarrrml, log):
            return {
                "format": "ttl",
                "output_dir": str(tmp_path),
                "total": len(urls),
                "success": 1,
                "failed": 0,
                "errors": [],
            }

    monkeypatch.setattr(orchestrator_module, "BatchGenerator", _FakeBatch)

    request = GenerateRequest(
        input_value="https://example.com/sitemap.xml",
        yarrrml_path=yarrrml_path,
        regex=".*",
        output_dir=tmp_path,
        output_format="ttl",
        concurrency="1",
        api_key="test-key",
        base_url=None,
        ssl_ca_cert=None,
        headed=False,
        timeout_ms=1000,
        wait_until="load",
        max_xhtml_chars=1000,
        max_text_node_chars=200,
        max_pages=None,
        verbose=False,
    )

    workflow = GenerateWorkflow()
    summary = workflow.run(request, log=lambda *_: None)

    assert summary["input"] == "https://example.com/sitemap.xml"
    assert summary["success"] == 1

from __future__ import annotations

import logging
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import wordlift_sdk.structured_data.engine as engine_module

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

from wordlift_sdk.structured_data.engine import (  # noqa: E402
    materialize_yarrrml_jsonld,
    normalize_yarrrml_mappings,
    postprocess_jsonld,
)
from wordlift_sdk.structured_data.materialization import MaterializationPipeline  # noqa: E402
from wordlift_sdk.utils.html_converter import HtmlConverter  # noqa: E402


def _install_materialization_stubs(
    monkeypatch: pytest.MonkeyPatch, capture: dict
) -> None:
    def _fake_materialize(
        input_path: Path, backend: str = "morph"
    ) -> dict[str, object]:
        del backend
        capture["mapping_path"] = str(input_path)
        capture["mapping_text"] = input_path.read_text()
        return {"@graph": []}

    monkeypatch.setattr(
        engine_module,
        "_materialize_jsonld",
        _fake_materialize,
    )


def test_mapping_types_preserved_as_authored(tmp_path: Path) -> None:
    yarrml = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
    po:
      - [a, 'schema:WebPage']
  product:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/product~iri
    po:
      - [a, 'schema:Product']
"""

    normalized, _ = normalize_yarrrml_mappings(
        yarrml,
        "https://example.com/page",
        tmp_path / "page.xhtml",
    )

    assert "schema:WebPage" in normalized
    assert "schema:Product" in normalized
    assert "schema:Review" not in normalized
    assert "schema:Thing" not in normalized
    assert "ex:" not in normalized


def test_no_specialized_postprocess_side_effects() -> None:
    raw = {
        "@graph": [
            {
                "@id": "https://example.com/review",
                "@type": ["https://schema.org/Review"],
                "https://schema.org/positiveNotes": [{"@value": "Same"}],
                "https://schema.org/negativeNotes": [{"@value": "Same"}],
            }
        ]
    }

    out = postprocess_jsonld(
        raw,
        mappings=[],
        xhtml="<html/>",
        dataset_uri="urn:dataset",
        url="https://example.com/review",
    )

    node = out["@graph"][0]
    assert "https://schema.org/positiveNotes" in node
    assert "https://schema.org/negativeNotes" in node
    assert "https://schema.org/url" not in node


def test_runtime_token_replacement_xhtml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
    po:
      - [a, 'schema:WebPage']
"""

    engine_module.materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        url="https://example.com/page",
    )

    assert "__XHTML__" not in capture["mapping_text"]
    assert (tmp_path / "page.xhtml").as_posix() in capture["mapping_text"]
    assert capture["mapping_path"].endswith("mapping.yarrrml")
    assert not (tmp_path / "work" / "mapping.ttl").exists()


def test_runtime_token_replacement_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    class _Response:
        web_page = types.SimpleNamespace(url="https://response.example/page")

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __URL__~iri
    po:
      - [a, 'schema:WebPage']
      - [schema:url, '__URL__']
"""

    engine_module.materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        response=_Response(),
        url="https://argument.example/page",
    )

    assert "https://response.example/page" in capture["mapping_text"]
    assert "https://argument.example/page" not in capture["mapping_text"]
    assert "__URL__" not in capture["mapping_text"]


def test_runtime_token_replacement_id_subject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __ID__~iri
    po:
      - [a, 'schema:WebPage']
"""

    class _Response:
        id = "https://example.com/imports/root-node"

    engine_module.materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        response=_Response(),
    )

    assert "__ID__" not in capture["mapping_text"]
    assert "https://example.com/imports/root-node~iri" in capture["mapping_text"]


def test_runtime_token_replacement_id_object_iri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
    po:
      - [a, 'schema:WebPage']
      - [schema:mainEntity, __ID__~iri]
"""

    class _Response:
        id = "https://example.com/imports/root-node"

    engine_module.materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        response=_Response(),
    )

    assert "__ID__" not in capture["mapping_text"]
    assert (
        "[schema:mainEntity, https://example.com/imports/root-node~iri]"
        in capture["mapping_text"]
    )


def test_id_token_without_runtime_id_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __ID__~iri
"""

    with pytest.raises(RuntimeError, match="__ID__"):
        engine_module.materialize_yarrrml_jsonld(
            mapping,
            xhtml_path=tmp_path / "page.xhtml",
            workdir=tmp_path / "work",
        )


def test_runtime_tokens_url_and_xhtml_regression_after_id_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __URL__~iri
    po:
      - [a, 'schema:WebPage']
      - [schema:url, '__URL__']
"""

    engine_module.materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        url="https://example.com/final",
    )

    assert "__XHTML__" not in capture["mapping_text"]
    assert "__URL__" not in capture["mapping_text"]
    assert (tmp_path / "page.xhtml").as_posix() in capture["mapping_text"]
    assert "https://example.com/final" in capture["mapping_text"]


def test_url_token_without_runtime_placeholder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __URL__~iri
    po:
      - [a, 'schema:WebPage']
      - [schema:url, '__URL__']
"""

    out = engine_module.materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        url="https://example.com/final",
    )

    assert out == {"@graph": []}
    assert "__URL__" not in capture["mapping_text"]
    assert "https://example.com/final" in capture["mapping_text"]


def test_materialization_uses_direct_yarrrml_without_ttl_transpile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
    po:
      - [a, 'schema:WebPage']
"""

    engine_module.materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
    )

    assert capture["mapping_path"].endswith("mapping.yarrrml")
    assert (tmp_path / "work" / "mapping.yarrrml").exists()
    assert not (tmp_path / "work" / "mapping.ttl").exists()


def test_unresolved_url_token_non_strict_keeps_token_and_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __URL__~iri
"""

    materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
    )

    assert "__URL__" in capture["mapping_text"]
    assert "no runtime URL is available" in caplog.text


def test_unresolved_url_token_strict_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}
    _install_materialization_stubs(monkeypatch, capture)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __URL__~iri
"""

    with pytest.raises(RuntimeError, match="__URL__"):
        engine_module.materialize_yarrrml_jsonld(
            mapping,
            xhtml_path=tmp_path / "page.xhtml",
            workdir=tmp_path / "work",
            strict_url_token=True,
        )


def test_runtime_url_precedence_in_materialization_pipeline_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}

    def _fake_materialize(
        input_path: Path, backend: str = "morph"
    ) -> dict[str, object]:
        del backend
        capture["mapping_path"] = str(input_path)
        capture["mapping_text"] = input_path.read_text()
        return {
            "@graph": [
                {
                    "@id": "https://example.com/node",
                    "@type": ["https://schema.org/WebPage"],
                }
            ]
        }

    monkeypatch.setattr(
        engine_module,
        "_materialize_jsonld",
        _fake_materialize,
    )

    class _Response:
        web_page = types.SimpleNamespace(url="https://response.example/page")

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __URL__~iri
"""

    materializer = MaterializationPipeline()
    materializer.run(
        yarrrml=mapping,
        url="https://argument.example/page",
        cleaned_xhtml="<html/>",
        dataset_uri="urn:dataset",
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        response=_Response(),
    )

    assert "https://response.example/page" in capture["mapping_text"]
    assert "https://argument.example/page" not in capture["mapping_text"]


def test_runtime_id_resolution_in_materialization_pipeline_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, str] = {}

    def _fake_materialize(
        input_path: Path, backend: str = "morph"
    ) -> dict[str, object]:
        del backend
        capture["mapping_path"] = str(input_path)
        capture["mapping_text"] = input_path.read_text()
        return {
            "@graph": [
                {
                    "@id": "https://example.com/node",
                    "@type": ["https://schema.org/WebPage"],
                }
            ]
        }

    monkeypatch.setattr(
        engine_module,
        "_materialize_jsonld",
        _fake_materialize,
    )

    class _Response:
        id = "https://response.example/web-page-imports/123"

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: __ID__~iri
"""

    materializer = MaterializationPipeline()
    materializer.run(
        yarrrml=mapping,
        url="https://argument.example/page",
        cleaned_xhtml="<html/>",
        dataset_uri="urn:dataset",
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        response=_Response(),
    )

    assert "https://response.example/web-page-imports/123" in capture["mapping_text"]


def test_malformed_yarrrml_raises_actionable_error(tmp_path: Path) -> None:
    malformed = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page: [
"""

    with pytest.raises(RuntimeError, match="Malformed YARRRML mapping"):
        materialize_yarrrml_jsonld(
            malformed,
            xhtml_path=tmp_path / "page.xhtml",
            workdir=tmp_path / "work",
        )


def test_unsupported_xpath_or_function_raises_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import wordlift_sdk.structured_data.engine as _engine

    class _FakeFuture:
        def result(self):
            raise ValueError("XPathEvalError: Unsupported function local-namez()")

    class _FakePool:
        def submit(self, fn, *args, **kwargs):
            return _FakeFuture()

    monkeypatch.setattr(_engine, "_get_morph_kgc_pool", lambda: _FakePool())

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
"""

    with pytest.raises(RuntimeError, match="Unsupported XPath/function construct"):
        materialize_yarrrml_jsonld(
            mapping,
            xhtml_path=tmp_path / "page.xhtml",
            workdir=tmp_path / "work",
        )


def _run_materialization_with_fake_morph_logging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    root_level: int,
) -> str:
    capture: dict[str, str] = {}
    mapping_partitioner_logger = logging.getLogger("mapping_partitioner")
    previous_root_level = logging.getLogger().level
    previous_mapping_partitioner_level = mapping_partitioner_logger.level

    class _FakeFuture:
        def __init__(self, config: str) -> None:
            self._config = config

        def result(self):
            capture["config"] = self._config
            if "logging_level = INFO" in self._config:
                mapping_partitioner_logger.info("INFO | mapping_partitioner")
            return engine_module.Graph().serialize(format="nt"), 0

    class _FakePool:
        def submit(self, _fn, config: str, _submit_time: float):
            return _FakeFuture(config)

    monkeypatch.setattr(engine_module, "_get_morph_kgc_pool", lambda: _FakePool())
    logging.getLogger().setLevel(root_level)
    mapping_partitioner_logger.setLevel(logging.NOTSET)

    try:
        materialize_yarrrml_jsonld(
            """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
    po:
      - [a, 'schema:WebPage']
""",
            xhtml_path=tmp_path / "page.xhtml",
            workdir=tmp_path / "work",
        )
    finally:
        logging.getLogger().setLevel(previous_root_level)
        mapping_partitioner_logger.setLevel(previous_mapping_partitioner_level)

    return capture.get("config", "")


def test_morph_logging_level_warning_omits_mapping_partitioner_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    config = _run_materialization_with_fake_morph_logging(
        monkeypatch,
        tmp_path,
        root_level=logging.WARNING,
    )

    assert "logging_level = WARNING" in config
    assert "INFO | mapping_partitioner" not in caplog.text


def test_morph_logging_level_info_allows_mapping_partitioner_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    config = _run_materialization_with_fake_morph_logging(
        monkeypatch,
        tmp_path,
        root_level=logging.INFO,
    )

    assert "logging_level = INFO" in config
    assert "INFO | mapping_partitioner" in caplog.text


def test_xpath_mapping_over_xhtml_callback_input_regression(tmp_path: Path) -> None:
    xhtml_path = tmp_path / "page.xhtml"
    xhtml_path.write_text(
        "<html><head><title>Example Title</title></head><body></body></html>"
    )

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/html']
    s: __URL__~iri
    po:
      - [a, 'schema:WebPage']
      - [schema:name, 'Example Title']
"""

    materializer = MaterializationPipeline()
    jsonld, _ = materializer.run(
        yarrrml=mapping,
        url="https://example.com/page",
        cleaned_xhtml=xhtml_path.read_text(),
        dataset_uri="urn:dataset",
        xhtml_path=xhtml_path,
        workdir=tmp_path / "work",
        strict_url_token=True,
    )

    names: list[str] = []
    for node in jsonld.get("@graph", []):
        value = node.get("https://schema.org/name")
        if value is None:
            value = node.get("http://schema.org/name")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "@value" in item:
                    names.append(item["@value"])
        elif isinstance(value, str):
            names.append(value)
    assert "Example Title" in names


def test_xpath_materialization_accepts_sanitized_xhtml_with_bad_prefixes(
    tmp_path: Path,
) -> None:
    raw_html = """
<html><body>
  <o:p xlink:href="https://example.com">Prefixed Heading</o:p>
</body></html>
"""
    xhtml = HtmlConverter().convert(raw_html)
    ET.fromstring(xhtml)

    xhtml_path = tmp_path / "page.xhtml"
    xhtml_path.write_text(xhtml)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/html/body']
    s: __URL__~iri
    po:
      - [a, 'schema:WebPage']
"""

    materializer = MaterializationPipeline()
    jsonld, _ = materializer.run(
        yarrrml=mapping,
        url="https://example.com/page",
        cleaned_xhtml=xhtml,
        dataset_uri="urn:dataset",
        xhtml_path=xhtml_path,
        workdir=tmp_path / "work",
        strict_url_token=True,
    )

    graph = jsonld.get("@graph", [])
    assert isinstance(graph, list)
    assert graph


def test_xpath_materialization_accepts_sanitized_xhtml_with_invalid_comments(
    tmp_path: Path,
) -> None:
    raw_html = """
<html><body><!--foo--bar--><h1>VPS</h1></body></html>
"""
    xhtml = HtmlConverter().convert(raw_html)
    ET.fromstring(xhtml)

    xhtml_path = tmp_path / "page.xhtml"
    xhtml_path.write_text(xhtml)

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/html/body']
    s: __URL__~iri
    po:
      - [a, 'schema:WebPage']
      - [schema:name, 'VPS']
"""

    materializer = MaterializationPipeline()
    jsonld, _ = materializer.run(
        yarrrml=mapping,
        url="https://example.com/vps",
        cleaned_xhtml=xhtml,
        dataset_uri="urn:dataset",
        xhtml_path=xhtml_path,
        workdir=tmp_path / "work",
        strict_url_token=True,
    )

    graph = jsonld.get("@graph", [])
    assert isinstance(graph, list)
    assert graph


def test_id_smoke_materialization_uses_runtime_response_id(
    tmp_path: Path,
) -> None:
    xhtml_path = tmp_path / "page.xhtml"
    xhtml_path.write_text("<html><head></head><body></body></html>")

    runtime_id = "https://example.com/web-page-imports/12345"
    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/html']
    s: __ID__~iri
    po:
      - [a, 'schema:WebPage']
      - [schema:name, 'Rooted Page']
      - [schema:mainEntity, __ID__~iri]
"""

    class _Response:
        id = runtime_id

    jsonld = materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=xhtml_path,
        workdir=tmp_path / "work",
        response=_Response(),
    )

    payload = str(jsonld)
    assert "__ID__" not in payload
    assert runtime_id in payload


# ---------------------------------------------------------------------------
# morph-kgc process pool: BrokenProcessPool recovery and pool sizing
# ---------------------------------------------------------------------------


def _make_ntriples_pool(ntriples: str):
    """Return a fake pool whose submit() returns (ntriples, 0)."""

    class _Future:
        def result(self):
            return ntriples, 0

    class _Pool:
        def submit(self, fn, *args, **kwargs):
            return _Future()

    return _Pool()


def _make_broken_pool():
    """Return a fake pool whose submit() raises BrokenProcessPool."""
    from concurrent.futures.process import BrokenProcessPool

    class _Future:
        def result(self):
            raise BrokenProcessPool("simulated crash")

    class _Pool:
        def submit(self, fn, *args, **kwargs):
            return _Future()

    return _Pool()


def test_broken_process_pool_retries_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call raises BrokenProcessPool; second succeeds with a fresh pool."""
    import wordlift_sdk.structured_data.engine as _engine
    from rdflib import Graph

    xhtml_path = tmp_path / "page.xhtml"
    xhtml_path.write_text("<html><head></head><body></body></html>")

    good_graph = Graph()
    ntriples = good_graph.serialize(format="nt")

    broken = _make_broken_pool()
    good = _make_ntriples_pool(ntriples)
    pools = iter([broken, good])

    monkeypatch.setattr(_engine, "_morph_kgc_pool", None)
    monkeypatch.setattr(_engine, "_morph_kgc_pool_max_workers", 0)
    monkeypatch.setattr(_engine, "_get_morph_kgc_pool", lambda: next(pools))

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
    po:
      - [a, 'schema:WebPage']
"""
    from wordlift_sdk.structured_data.engine import materialize_yarrrml_jsonld

    result = materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=xhtml_path,
        workdir=tmp_path / "work",
    )
    assert isinstance(result, (dict, list))


def test_broken_process_pool_twice_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two consecutive BrokenProcessPool errors must raise RuntimeError."""
    import wordlift_sdk.structured_data.engine as _engine

    xhtml_path = tmp_path / "page.xhtml"
    xhtml_path.write_text("<html><head></head><body></body></html>")

    pools = iter([_make_broken_pool(), _make_broken_pool()])

    monkeypatch.setattr(_engine, "_morph_kgc_pool", None)
    monkeypatch.setattr(_engine, "_morph_kgc_pool_max_workers", 0)
    monkeypatch.setattr(_engine, "_get_morph_kgc_pool", lambda: next(pools))

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
"""
    from wordlift_sdk.structured_data.engine import materialize_yarrrml_jsonld

    with pytest.raises(RuntimeError, match="broke twice"):
        materialize_yarrrml_jsonld(
            mapping,
            xhtml_path=xhtml_path,
            workdir=tmp_path / "work",
        )


def test_init_morph_kgc_pool_is_noop_when_pool_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """init_morph_kgc_pool must not replace an already-existing pool."""
    import wordlift_sdk.structured_data.engine as _engine

    sentinel = object()
    monkeypatch.setattr(_engine, "_morph_kgc_pool", sentinel)
    monkeypatch.setattr(_engine, "_morph_kgc_pool_max_workers", 2)

    _engine.init_morph_kgc_pool(8)

    assert _engine._morph_kgc_pool is sentinel


def test_get_morph_kgc_pool_reuses_max_workers_after_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a pool reset, _get_morph_kgc_pool recreates with the stored worker count."""
    import wordlift_sdk.structured_data.engine as _engine

    created_with: list[int] = []

    class _FakePool:
        def __init__(self, max_workers: int, **_kwargs):
            created_with.append(max_workers)

    monkeypatch.setattr(_engine, "_morph_kgc_pool", None)
    monkeypatch.setattr(_engine, "_morph_kgc_pool_max_workers", 6)
    monkeypatch.setattr(
        _engine,
        "ProcessPoolExecutor",
        lambda max_workers, **kw: _FakePool(max_workers, **kw),
    )

    pool = _engine._get_morph_kgc_pool()
    assert isinstance(pool, _FakePool)
    assert created_with == [6]


def test_materialization_worph_backend_uses_worph_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import wordlift_sdk.structured_data.engine as _engine

    xhtml_path = tmp_path / "page.xhtml"
    xhtml_path.write_text("<html><head></head><body></body></html>")

    used: dict[str, bool] = {"worph": False}

    class _Future:
        def result(self):
            g = engine_module.Graph()
            return g.serialize(format="nt"), 0

    class _WorphPool:
        def submit(self, fn, *args, **kwargs):
            used["worph"] = True
            return _Future()

    monkeypatch.setattr(_engine, "_get_worph_pool", lambda: _WorphPool())

    mapping = """
prefixes:
  schema: 'https://schema.org/'
mappings:
  page:
    sources:
      - [__XHTML__~xpath, '/']
    s: https://example.com/page~iri
    po:
      - [a, 'schema:WebPage']
"""
    out = materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=xhtml_path,
        workdir=tmp_path / "work",
        materialization_backend="worph",
    )
    assert isinstance(out, (dict, list))
    assert used["worph"] is True

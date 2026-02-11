from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

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

_pyshacl = types.ModuleType("pyshacl")


def _stub_validate(*_args, **_kwargs):
    return None, None, None


_pyshacl.validate = _stub_validate
sys.modules.setdefault("pyshacl", _pyshacl)

from wordlift_sdk.structured_data.engine import (  # noqa: E402
    materialize_yarrrml_jsonld,
    normalize_yarrrml_mappings,
    postprocess_jsonld,
)
from wordlift_sdk.structured_data.materialization import MaterializationPipeline  # noqa: E402


def _install_materialization_stubs(
    monkeypatch: pytest.MonkeyPatch, capture: dict
) -> None:
    def _fake_materialize(input_path: Path) -> dict[str, object]:
        capture["mapping_path"] = str(input_path)
        capture["mapping_text"] = input_path.read_text()
        return {"@graph": []}

    monkeypatch.setattr(
        "wordlift_sdk.structured_data.engine._materialize_jsonld",
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

    materialize_yarrrml_jsonld(
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

    materialize_yarrrml_jsonld(
        mapping,
        xhtml_path=tmp_path / "page.xhtml",
        workdir=tmp_path / "work",
        response=_Response(),
        url="https://argument.example/page",
    )

    assert "https://response.example/page" in capture["mapping_text"]
    assert "https://argument.example/page" not in capture["mapping_text"]
    assert "__URL__" not in capture["mapping_text"]


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

    out = materialize_yarrrml_jsonld(
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

    materialize_yarrrml_jsonld(
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
        materialize_yarrrml_jsonld(
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

    def _fake_materialize(input_path: Path) -> dict[str, object]:
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
        "wordlift_sdk.structured_data.engine._materialize_jsonld",
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
    fake_morph = types.SimpleNamespace(
        materialize=lambda _cfg: (_ for _ in ()).throw(
            ValueError("XPathEvalError: Unsupported function local-namez()")
        )
    )
    monkeypatch.setitem(sys.modules, "morph_kgc", fake_morph)

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

from __future__ import annotations

import importlib
import sys

import pytest


# Modules that own ProcessPoolExecutors must not be evicted — dropping them
# causes function-identity mismatches when the pool tries to pickle workers.
_PRESERVE_MODULES = frozenset(
    [
        "wordlift_sdk.structured_data.engine",
        "wordlift_sdk.validation.shacl_validation_service",
        "wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler",
        "wordlift_sdk.workflow.url_handler.web_page_scrape_url_handler",
    ]
)


def _drop_modules(prefix: str) -> None:
    for name in list(sys.modules):
        if name in _PRESERVE_MODULES:
            continue
        if name == prefix or name.startswith(f"{prefix}."):
            sys.modules.pop(name, None)


def test_root_package_import_is_lazy(monkeypatch: pytest.MonkeyPatch):
    _drop_modules("wordlift_sdk")

    package = importlib.import_module("wordlift_sdk")

    assert "wordlift_sdk.main" not in sys.modules

    import types

    stub_main = types.ModuleType("wordlift_sdk.main")
    stub_main.run_kg_import_workflow = object()  # type: ignore[attr-defined]

    def fake_import_module(name: str):
        if name == "wordlift_sdk.main":
            sys.modules["wordlift_sdk.main"] = stub_main
            return stub_main
        return importlib.import_module(name)

    monkeypatch.setattr("wordlift_sdk._lazy_exports.import_module", fake_import_module)

    package.run_kg_import_workflow

    assert "wordlift_sdk.main" in sys.modules


def test_feature_package_import_is_lazy(monkeypatch: pytest.MonkeyPatch):
    _drop_modules("wordlift_sdk.render")

    package = importlib.import_module("wordlift_sdk.render")

    assert "wordlift_sdk.render.html_renderer" not in sys.modules

    import types

    stub_renderer = types.ModuleType("wordlift_sdk.render.html_renderer")
    stub_renderer.HtmlRenderer = object()  # type: ignore[attr-defined]

    def fake_import_module(name: str):
        if name == "wordlift_sdk.render.html_renderer":
            sys.modules["wordlift_sdk.render.html_renderer"] = stub_renderer
            return stub_renderer
        return importlib.import_module(name)

    monkeypatch.setattr("wordlift_sdk._lazy_exports.import_module", fake_import_module)

    package.HtmlRenderer

    assert "wordlift_sdk.render.html_renderer" in sys.modules


def test_feature_export_reports_matching_extra(monkeypatch: pytest.MonkeyPatch):
    _drop_modules("wordlift_sdk.validation")
    package = importlib.import_module("wordlift_sdk.validation")

    def fake_import_module(name: str):
        if name == "wordlift_sdk.validation.shacl":
            raise ModuleNotFoundError("No module named 'pyshacl'", name="pyshacl")
        return importlib.import_module(name)

    monkeypatch.setattr("wordlift_sdk._lazy_exports.import_module", fake_import_module)

    with pytest.raises(ModuleNotFoundError) as excinfo:
        package.validate_file

    assert "wordlift-sdk[validation]" in str(excinfo.value)


def test_workflow_export_reports_matching_extra(monkeypatch: pytest.MonkeyPatch):
    _drop_modules("wordlift_sdk")
    package = importlib.import_module("wordlift_sdk")

    def fake_import_module(name: str):
        if name == "wordlift_sdk.main":
            raise ModuleNotFoundError("No module named 'gql'", name="gql")
        return importlib.import_module(name)

    monkeypatch.setattr("wordlift_sdk._lazy_exports.import_module", fake_import_module)

    with pytest.raises(ModuleNotFoundError) as excinfo:
        package.run_kg_import_workflow

    assert "wordlift-sdk[workflow]" in str(excinfo.value)

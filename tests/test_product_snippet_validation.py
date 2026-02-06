from pathlib import Path
import importlib.util
import json
import sys

import pytest

from wordlift_sdk.validation import shacl


def _load_real_validate(monkeypatch: pytest.MonkeyPatch):
    if "pyshacl" in sys.modules:
        monkeypatch.delitem(sys.modules, "pyshacl", raising=False)
    spec = importlib.util.find_spec("pyshacl")
    if spec is None or spec.loader is None:
        raise RuntimeError("pyshacl is required for this test.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate


def test_product_snippet_offers_satisfies_one_of(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shacl, "validate", _load_real_validate(monkeypatch))

    fixture = Path("tests/fixtures/product_snippet_offers.jsonld")
    data = json.loads(fixture.read_text(encoding="utf-8"))

    for node in data:
        if isinstance(node, dict) and isinstance(node.get("@context"), str):
            node["@context"] = {"@vocab": "http://schema.org/"}

    normalized = tmp_path / "product_snippet_offers.jsonld"
    normalized.write_text(json.dumps(data), encoding="utf-8")

    result = shacl.validate_file(
        normalized.as_posix(),
        shape_specs=["google-product-snippet"],
    )

    assert result.conforms is True, result.report_text


def test_product_snippet_aggregate_offer_satisfies_one_of(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shacl, "validate", _load_real_validate(monkeypatch))

    fixture = Path("tests/fixtures/product_snippet_aggregate_offer.jsonld")
    data = json.loads(fixture.read_text(encoding="utf-8"))

    for node in data:
        if isinstance(node, dict) and isinstance(node.get("@context"), str):
            node["@context"] = {"@vocab": "http://schema.org/"}

    normalized = tmp_path / "product_snippet_aggregate_offer.jsonld"
    normalized.write_text(json.dumps(data), encoding="utf-8")

    result = shacl.validate_file(
        normalized.as_posix(),
        shape_specs=["google-product-snippet"],
    )

    assert result.conforms is True, result.report_text

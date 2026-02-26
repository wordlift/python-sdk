import importlib.util
import json
import sys
from pathlib import Path

import pytest

from wordlift_sdk.validation import shacl
from wordlift_sdk.validation.shacl import extract_validation_issues


def _load_real_validate(monkeypatch: pytest.MonkeyPatch):
    if "pyshacl" in sys.modules:
        monkeypatch.delitem(sys.modules, "pyshacl", raising=False)
    spec = importlib.util.find_spec("pyshacl")
    if spec is None or spec.loader is None:
        raise RuntimeError("pyshacl is required for this test.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate


def test_merchant_listing_defined_region_address_country_only_is_warning_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shacl, "validate", _load_real_validate(monkeypatch))

    payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@id": "https://data.wordlift.io/wl1506344/merchant-return-policys/shipping-policy/offer-shipping-details/offer-shipping-details-1/defined-regions/defined-region",
        "@type": "DefinedRegion",
        "addressCountry": "CA",
    }
    source = tmp_path / "defined-region.jsonld"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = shacl.validate_file(
        source.as_posix(),
        shape_specs=["google-merchant-listing"],
    )
    issues = extract_validation_issues(result)

    assert result.conforms is True, result.report_text
    assert result.warning_count == 1
    assert len(issues) == 1
    assert (
        issues[0].message
        == "Recommended by Google: choose either addressRegion or postalCode."
    )
    assert issues[0].result_path is None


def test_defined_region_address_country_only_conforms_with_default_shapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shacl, "validate", _load_real_validate(monkeypatch))

    payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@id": "https://data.wordlift.io/wl1506344/merchant-return-policys/shipping-policy/offer-shipping-details/offer-shipping-details-1/defined-regions/defined-region",
        "@type": "DefinedRegion",
        "addressCountry": "CA",
    }
    source = tmp_path / "defined-region-default-shapes.jsonld"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = shacl.validate_file(source.as_posix())

    assert result.conforms is True, result.report_text

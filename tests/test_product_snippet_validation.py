from pathlib import Path
import json

from wordlift_sdk.validation import shacl


def test_product_snippet_offers_satisfies_one_of(
    tmp_path: Path,
) -> None:
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
    tmp_path: Path,
) -> None:
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

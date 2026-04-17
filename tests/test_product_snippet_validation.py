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


def test_schemaorg_grammar_price_specification_accepts_unit_price_specification(
    tmp_path: Path,
) -> None:
    payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@graph": [
            {
                "@id": "https://example.com/offers/o1",
                "@type": "Offer",
                "priceSpecification": {"@id": "https://example.com/price-specs/ps1"},
            },
            {
                "@id": "https://example.com/price-specs/ps1",
                "@type": "UnitPriceSpecification",
                "price": 10.0,
                "priceCurrency": "USD",
            },
        ],
    }
    path = tmp_path / "schemaorg-price-spec-ok.jsonld"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = shacl.validate_file(path.as_posix(), shape_specs=["schemaorg-grammar"])
    messages = [issue.message for issue in shacl.extract_validation_issues(result)]

    assert "Schema.org range check: priceSpecification." not in messages


def test_schemaorg_grammar_price_specification_rejects_invalid_type(
    tmp_path: Path,
) -> None:
    payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@graph": [
            {
                "@id": "https://example.com/offers/o1",
                "@type": "Offer",
                "priceSpecification": {"@id": "https://example.com/price-specs/ps1"},
            },
            {
                "@id": "https://example.com/price-specs/ps1",
                "@type": "Thing",
                "name": "invalid price specification type",
            },
        ],
    }
    path = tmp_path / "schemaorg-price-spec-bad.jsonld"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = shacl.validate_file(path.as_posix(), shape_specs=["schemaorg-grammar"])
    messages = [issue.message for issue in shacl.extract_validation_issues(result)]

    assert "Schema.org range check: priceSpecification." in messages

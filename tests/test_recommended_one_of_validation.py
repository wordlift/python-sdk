import json
from pathlib import Path

from wordlift_sdk.validation import shacl
from wordlift_sdk.validation.shacl import extract_validation_issues


def _write_jsonld(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _messages_for(result) -> list[str]:
    return [issue.message for issue in extract_validation_issues(result)]


def test_dataset_recommended_either_or_is_warning_only(
    tmp_path: Path,
) -> None:
    missing_payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@type": "Dataset",
        "name": "Dataset Name",
        # Google: Dataset description must be 50-5000 characters.
        "description": "Dataset Description " + "x" * 40,
    }
    with_has_part_payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@type": "Dataset",
        "name": "Dataset Name",
        # Google: Dataset description must be 50-5000 characters.
        "description": "Dataset Description " + "x" * 40,
        "hasPart": "urn:dataset:part-a",
    }

    missing_path = _write_jsonld(tmp_path, "dataset-missing.jsonld", missing_payload)
    with_has_part_path = _write_jsonld(
        tmp_path, "dataset-has-part.jsonld", with_has_part_payload
    )

    missing_result = shacl.validate_file(
        missing_path.as_posix(),
        shape_specs=["google-dataset"],
    )
    with_has_part_result = shacl.validate_file(
        with_has_part_path.as_posix(),
        shape_specs=["google-dataset"],
    )

    missing_messages = _messages_for(missing_result)
    with_has_part_messages = _messages_for(with_has_part_result)
    expected = "Every Dataset should have at least one of hasPart or isPartOf."

    assert missing_result.conforms is True, missing_result.report_text
    assert expected in missing_messages
    assert with_has_part_result.conforms is True, with_has_part_result.report_text
    assert expected not in with_has_part_messages


def _product_with_shipping_rate(rate: dict) -> dict:
    # The new merchant rules check shipping details only under a Product's Offer,
    # and require image, shippingDestination and deliveryTime.
    quantity = {"@type": "QuantitativeValue", "minValue": 0, "maxValue": 1}
    return {
        "@context": {"@vocab": "http://schema.org/"},
        "@type": "OfferShippingDetails",
        "shippingRate": {"@type": "MonetaryAmount", "currency": "CAD", "value": "9.99"},
    }

    missing_path = _write_jsonld(
        tmp_path, "offer-shipping-details-missing.jsonld", missing_payload
    )
    with_value_path = _write_jsonld(
        tmp_path, "offer-shipping-details-with-value.jsonld", with_value_payload
    )

    missing_result = shacl.validate_file(
        missing_path.as_posix(),
        shape_specs=["google-merchant-listing"],
    )
    with_value_result = shacl.validate_file(
        with_value_path.as_posix(),
        shape_specs=["google-merchant-listing"],
    )

    missing_messages = _messages_for(missing_result)
    with_value_messages = _messages_for(with_value_result)
    expected = "Recommended by Google: choose either shippingRate.maxValue or shippingRate.value."

    assert missing_result.conforms is True, missing_result.report_text
    assert expected in missing_messages
    assert with_value_result.conforms is True, with_value_result.report_text
    assert expected not in with_value_messages


def test_product_offer_price_currency_recommended_either_or_is_warning_only(
    tmp_path: Path,
) -> None:
    missing_payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@type": "Product",
        "name": "Sample product",
        "offers": {"@type": "Offer", "price": "10.00"},
    }
    with_price_currency_payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@type": "Product",
        "name": "Sample product",
        "offers": {"@type": "Offer", "price": "10.00", "priceCurrency": "USD"},
    }

    missing_path = _write_jsonld(
        tmp_path, "product-offer-missing-currency-alt.jsonld", missing_payload
    )
    with_price_currency_path = _write_jsonld(
        tmp_path, "product-offer-with-currency.jsonld", with_price_currency_payload
    )

    missing_result = shacl.validate_file(
        missing_path.as_posix(),
        shape_specs=["google-product-snippet"],
    )
    with_price_currency_result = shacl.validate_file(
        with_price_currency_path.as_posix(),
        shape_specs=["google-product-snippet"],
    )

    missing_messages = _messages_for(missing_result)
    with_price_currency_messages = _messages_for(with_price_currency_result)
    expected = (
        "Each non-aggregate Offer of the page's Product should have priceCurrency "
        "or priceSpecification.priceCurrency."
    )

    assert missing_result.conforms is True, missing_result.report_text
    assert expected in missing_messages
    assert with_price_currency_result.conforms is True, (
        with_price_currency_result.report_text
    )
    assert expected not in with_price_currency_messages

import json
from pathlib import Path

from wordlift_sdk.validation import shacl
from wordlift_sdk.validation.shacl import extract_validation_issues


def test_merchant_listing_defined_region_address_country_only_is_warning_only(
    tmp_path: Path,
) -> None:
    # New merchant rules check DefinedRegion only under an OfferShippingDetails'
    # shippingDestination of a Product with offers (context types are never
    # checked globally), so the region is nested in a full Product.
    payload = {
        "@context": {"@vocab": "http://schema.org/"},
        "@type": "Product",
        "name": "Sample product",
        "image": "https://example.com/p.jpg",
        "offers": {
            "@type": "Offer",
            "price": "10.00",
            "priceCurrency": "CAD",
            "availability": "https://schema.org/InStock",
            "shippingDetails": {
                "@type": "OfferShippingDetails",
                "shippingRate": {
                    "@type": "MonetaryAmount",
                    "currency": "CAD",
                    "value": "9.99",
                },
                "deliveryTime": {
                    "@type": "ShippingDeliveryTime",
                    "handlingTime": {
                        "@type": "QuantitativeValue",
                        "minValue": 0,
                        "maxValue": 1,
                        "unitCode": "DAY",
                    },
                    "transitTime": {
                        "@type": "QuantitativeValue",
                        "minValue": 1,
                        "maxValue": 3,
                        "unitCode": "DAY",
                    },
                },
                "shippingDestination": {
                    "@type": "DefinedRegion",
                    "addressCountry": "CA",
                },
            },
        },
    }
    source = tmp_path / "defined-region.jsonld"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = shacl.validate_file(
        source.as_posix(),
        shape_specs=["google-merchant-listing"],
    )
    issues = extract_validation_issues(result)
    region_issues = [
        i
        for i in issues
        if i.message
        == "the DefinedRegion under an OfferShippingDetails' shippingDestination "
        "should have addressRegion or postalCode."
    ]

    # An exact warning count is not asserted: the many other recommended Product
    # and Offer properties also warn. The rule under test must be present and
    # warning-level, and nothing may be an error.
    assert result.conforms is True, result.report_text
    assert len(region_issues) == 1
    assert region_issues[0].level == "warning"
    assert not [i for i in issues if i.level == "error"]


def test_defined_region_address_country_only_conforms_with_default_shapes(
    tmp_path: Path,
) -> None:
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

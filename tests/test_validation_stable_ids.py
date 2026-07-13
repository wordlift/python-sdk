from __future__ import annotations

from wordlift_sdk.validation import shacl


# ---------------------------------------------------------------------------
# assign_stable_jsonld_ids
# ---------------------------------------------------------------------------


def test_assign_stable_ids_adds_pointer_based_ids() -> None:
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": "Widget",
                "offers": {"@type": "Offer", "price": "9.99"},
            }
        ],
    }
    out = shacl.assign_stable_jsonld_ids(data)
    product = out["@graph"][0]
    assert product["@id"] == "urn:wl:node:/@graph/0"
    assert product["offers"]["@id"] == "urn:wl:node:/@graph/0/offers"
    # the input is not mutated
    assert "@id" not in data["@graph"][0]


def test_assign_stable_ids_is_deterministic() -> None:
    data = {"@type": "Product", "brand": {"@type": "Brand", "name": "X"}}
    assert shacl.assign_stable_jsonld_ids(data) == shacl.assign_stable_jsonld_ids(data)


def test_assign_stable_ids_preserves_existing_id_and_skips_value_objects() -> None:
    data = {
        "@type": "Product",
        "@id": "https://example.com/p",
        "released": {
            "@value": "2024-01-01",
            "@type": "http://www.w3.org/2001/XMLSchema#date",
        },
    }
    out = shacl.assign_stable_jsonld_ids(data)
    assert out["@id"] == "https://example.com/p"  # existing id kept
    assert "@id" not in out["released"]  # literal value object untouched


def test_assign_stable_ids_handles_lists_of_nodes() -> None:
    data = [{"@type": "Offer"}, {"@type": "Offer"}]
    out = shacl.assign_stable_jsonld_ids(data)
    assert out[0]["@id"] == "urn:wl:node:/0"
    assert out[1]["@id"] == "urn:wl:node:/1"


def test_assign_stable_ids_ignores_scalars() -> None:
    assert shacl.assign_stable_jsonld_ids("plain") == "plain"
    assert shacl.assign_stable_jsonld_ids({"name": "x"})["@id"] == "urn:wl:node:/"


def test_assign_stable_ids_rfc6901_escapes_keys() -> None:
    # A node nested under a key containing '/' must produce a valid RFC 6901
    # pointer ('/' -> '~1', '~' -> '~0') so it can be resolved unambiguously.
    data = {
        "@type": "Product",
        "https://ref.gs1.org/voc/isNestedUnder": {"@type": "Offer"},
    }
    out = shacl.assign_stable_jsonld_ids(data)
    nested_id = out["https://ref.gs1.org/voc/isNestedUnder"]["@id"]
    assert nested_id == "urn:wl:node:/https:~1~1ref.gs1.org~1voc~1isNestedUnder"

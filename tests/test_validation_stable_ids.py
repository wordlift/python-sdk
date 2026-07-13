from __future__ import annotations

import re

from rdflib import BNode, Graph, URIRef
from rdflib.collection import Collection

from wordlift_sdk.validation import shacl

_BNODE_HASH = re.compile(r"[Nn][0-9a-f]{8,}")


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


# ---------------------------------------------------------------------------
# format_shacl_path
# ---------------------------------------------------------------------------


def test_format_shacl_path_simple_uri() -> None:
    assert shacl.format_shacl_path(URIRef("http://schema.org/price")) == "price"
    assert shacl.format_shacl_path(URIRef("https://schema.org/price")) == "price"


def test_format_shacl_path_sequence_path() -> None:
    shapes = Graph()
    head = BNode()
    Collection(
        shapes,
        head,
        [
            URIRef("http://schema.org/address"),
            URIRef("http://schema.org/addressCountry"),
        ],
    )
    assert shacl.format_shacl_path(head, shapes) == "address.addressCountry"


def test_format_shacl_path_blank_node_without_shapes_returns_none() -> None:
    # Never emit a raw blank-node label as a property path.
    assert shacl.format_shacl_path(BNode(), None) is None
    assert shacl.format_shacl_path(BNode(), Graph()) is None
    assert shacl.format_shacl_path(None) is None


# ---------------------------------------------------------------------------
# End-to-end: stable, resolvable focus nodes through the real validator
# ---------------------------------------------------------------------------


def _validate(payload: dict) -> shacl.ValidationResult:
    graph = shacl._load_graph_from_jsonld(payload)
    validator = shacl.PreparedShaclValidator.from_shape_specs()
    result = validator.validate_graph(graph)
    return shacl.ValidationResult(
        conforms=result.conforms,
        report_text=result.report_text,
        report_graph=result.report_graph,
        data_graph=result.data_graph,
        shape_source_map=validator.prepared_shapes.shape_source_map,
        warning_count=result.warning_count,
        shapes_graph=validator.prepared_shapes.shapes_graph,
    )


def test_focus_nodes_and_paths_are_stable_and_never_blank_hashes() -> None:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": "Widget",
                # nested, @id-less Offer -> would be a random blank node without the fix
                "offers": {"@type": "Offer", "priceCurrency": "USD"},
            }
        ],
    }

    issues_first = shacl.extract_validation_issues(_validate(payload))
    issues_second = shacl.extract_validation_issues(_validate(payload))

    assert issues_first, "expected at least one validation issue"

    for issue in issues_first:
        assert not _BNODE_HASH.fullmatch(issue.focus_node or "")
        assert issue.focus_node is None or issue.focus_node.startswith("urn:wl:node:")
        assert not _BNODE_HASH.fullmatch(issue.result_path or "")

    # Focus nodes are identical across independent parses (blank-node labels are not).
    assert {i.focus_node for i in issues_first} == {i.focus_node for i in issues_second}

    # The nested Offer is individually addressable.
    assert any(i.focus_node == "urn:wl:node:/@graph/0/offers" for i in issues_first)

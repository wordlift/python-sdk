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
# build_node_pointer_map
# ---------------------------------------------------------------------------


def test_pointer_map_covers_real_ids_and_id_less_nodes() -> None:
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "@id": "https://acme.example/product/widget",
                "name": "Widget",
                "offers": {"@type": "Offer", "priceCurrency": "USD"},
            }
        ],
    }
    mapping = shacl._build_node_pointer_map(data)
    # a node with a real @id maps to its own document position
    assert mapping["https://acme.example/product/widget"] == "/@graph/0"
    # an @id-less node is keyed by the same urn: id the injector would give it
    assert mapping["urn:wl:node:/@graph/0/offers"] == "/@graph/0/offers"


def test_pointer_map_keys_match_injected_ids() -> None:
    # The map's synthetic keys must equal the @ids assign_stable_jsonld_ids
    # injects for the same document — otherwise findings would not resolve.
    data = {
        "@context": "https://schema.org",
        "@graph": [{"@type": "Product", "offers": {"@type": "Offer"}}],
    }
    injected = shacl.assign_stable_jsonld_ids(data)
    mapping = shacl._build_node_pointer_map(data)
    synthetic_ids = [
        node["@id"]
        for _pointer, node in shacl._iter_jsonld_nodes(injected)
        if node.get("@id", "").startswith("urn:wl:node:")
    ]
    assert synthetic_ids  # the fixture has @id-less nodes
    for node_id in synthetic_ids:
        assert node_id in mapping


def test_pointer_map_richest_occurrence_wins_for_duplicate_ids() -> None:
    # The same @id may appear as a bare reference stub and a full definition; SHACL
    # sees one merged resource, so we map it to the richest occurrence (the node
    # someone would actually edit), not blindly to the first one.
    data = {
        "@graph": [
            {"@id": "https://acme.example/brand"},  # stub, first but empty
            {
                "@type": "Product",
                "brand": {"@id": "https://acme.example/brand", "name": "Acme"},
            },
        ]
    }
    mapping = shacl._build_node_pointer_map(data)
    assert mapping["https://acme.example/brand"] == "/@graph/1/brand"


def test_pointer_map_richest_occurrence_wins_regardless_of_order() -> None:
    # The definition wins even when it precedes the stub — the choice is by
    # richness, not document order.
    data = {
        "@graph": [
            {
                "@type": "Product",
                "brand": {"@id": "https://acme.example/brand", "name": "Acme"},
            },
            {"@id": "https://acme.example/brand"},  # stub, last
        ]
    }
    mapping = shacl._build_node_pointer_map(data)
    assert mapping["https://acme.example/brand"] == "/@graph/0/brand"


def test_pointer_map_richness_ignores_type_and_context_keys() -> None:
    # Non-keyword properties should decide which node is the richest.
    data = {
        "@graph": [
            {"@id": "brand", "@type": "Brand", "@context": "https://schema.org"},  # 0 real props
            {"@id": "brand", "@type": "Brand", "name": "Acme"},  # 1 real prop
        ]
    }
    mapping = shacl._build_node_pointer_map(data)
    assert mapping["brand"] == "/@graph/1"


def test_pointer_map_ties_keep_first_occurrence() -> None:
    # Equally rich occurrences fall back to first document order so the map stays
    # deterministic across runs.
    data = {
        "@graph": [
            {"@id": "https://acme.example/brand", "name": "Acme"},  # richness 1, first
            {
                "@type": "Product",
                "brand": {"@id": "https://acme.example/brand", "logo": "x"},  # richness 1
            },
        ]
    }
    mapping = shacl._build_node_pointer_map(data)
    assert mapping["https://acme.example/brand"] == "/@graph/0"


def test_pointer_map_escapes_rfc6901_keys() -> None:
    data = {
        "@type": "Product",
        "https://ref.gs1.org/voc/isNestedUnder": {"@type": "Offer"},
    }
    mapping = shacl._build_node_pointer_map(data)
    assert (
        mapping["urn:wl:node:/https:~1~1ref.gs1.org~1voc~1isNestedUnder"]
        == "/https:~1~1ref.gs1.org~1voc~1isNestedUnder"
    )


def test_pointer_map_root_node() -> None:
    assert shacl._build_node_pointer_map({"name": "x"})["urn:wl:node:/"] == "/"


# ---------------------------------------------------------------------------
# resolve_focus_node
# ---------------------------------------------------------------------------


def test_resolve_focus_node_keeps_real_id() -> None:
    # A real @id is a public identifier; it is returned as-is alongside its pointer.
    public_id, pointer = shacl._resolve_focus_node(
        "https://acme.example/product", {"https://acme.example/product": "/@graph/0"}
    )
    assert public_id == "https://acme.example/product"
    assert pointer == "/@graph/0"


def test_resolve_focus_node_hides_synthetic_id() -> None:
    # A synthetic urn:wl:node: id is internal: public_id is None, only the pointer
    # crosses the boundary. Consumers never see the convention.
    public_id, pointer = shacl._resolve_focus_node(
        "urn:wl:node:/@graph/0/offers", {"urn:wl:node:/@graph/0/offers": "/@graph/0/offers"}
    )
    assert public_id is None
    assert pointer == "/@graph/0/offers"


def test_resolve_focus_node_handles_none_and_unmapped() -> None:
    assert shacl._resolve_focus_node(None, {}) == (None, None)
    # An @id absent from the map yields no pointer, but the id still passes through.
    assert shacl._resolve_focus_node("https://acme.example/x", {}) == (
        "https://acme.example/x",
        None,
    )


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


def _resolved_pointers(payload: dict) -> set[str]:
    """Resolve every finding's raw ``sh:focusNode`` to its JSON pointer, the way a
    consumer does: report focus + :func:`_build_node_pointer_map` over the original
    document."""
    result = _validate(payload)
    pointer_map = shacl._build_node_pointer_map(payload)
    pointers: set[str] = set()
    for node in result.report_graph.subjects(shacl.SH.resultSeverity, None):
        focus = result.report_graph.value(node, shacl.SH.focusNode)
        _, pointer = shacl._resolve_focus_node(
            str(focus) if focus is not None else None, pointer_map
        )
        if pointer is not None:
            pointers.add(pointer)
    return pointers


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

    issues = shacl.extract_validation_issues(_validate(payload))
    assert issues, "expected at least one validation issue"

    # Both nodes are anonymous, so focus_node stays anonymous: never the internal
    # urn:wl:node: id, never a random blank-node label — just None. result_path is a
    # readable property name, never a blank-node hash.
    for issue in issues:
        assert issue.focus_node is None
        assert not _BNODE_HASH.fullmatch(issue.result_path or "")

    # The stable, resolvable handle is the JSON pointer. It is identical across
    # independent parses (blank-node labels are not), and makes the nested @id-less
    # Offer individually addressable.
    pointers_first = _resolved_pointers(payload)
    pointers_second = _resolved_pointers(payload)
    assert pointers_first == pointers_second
    assert "/@graph/0/offers" in pointers_first


def test_scrub_synthetic_ids_strips_prefix_to_pointer() -> None:
    assert (
        shacl._scrub_synthetic_ids(
            "Less than 1 values on <urn:wl:node:/@graph/0>-><http://schema.org/url>"
        )
        == "Less than 1 values on </@graph/0>-><http://schema.org/url>"
    )
    assert shacl._scrub_synthetic_ids("urn:wl:node:/@graph/0/offers") == "/@graph/0/offers"
    assert shacl._scrub_synthetic_ids("no synthetic id here") == "no synthetic id here"
    assert shacl._scrub_synthetic_ids(None) is None


def test_urn_never_leaks_into_reported_output() -> None:
    # A payload that triggers a MinCount message ("Less than 1 values on <urn...>")
    # and a nested @id-less value node — both classic urn leak vectors.
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": "Widget",
                "offers": {"@type": "Offer", "priceCurrency": "USD"},
            }
        ],
    }
    result = _validate(payload)

    # Human-readable report is output -> scrubbed.
    assert "urn:wl:node:" not in result.report_text

    # Structured issues -> no urn in any user-facing field.
    issues = shacl.extract_validation_issues(result)
    assert issues
    for issue in issues:
        assert "urn:wl:node:" not in (issue.message or "")
        assert "urn:wl:node:" not in (issue.focus_node or "")

    # ...but the internal report graph still carries the urn focus nodes: the SDK
    # resolves JSON pointers from them, so they must survive there (not user-facing).
    assert any(
        "urn:wl:node:" in str(obj)
        for obj in result.report_graph.objects(None, shacl.SH.focusNode)
    )


def test_extract_resolves_node_pointer_and_stays_urn_free() -> None:
    # @id-less Product + nested @id-less Offer: focus_node has no real @id, so the
    # only handle is the resolved node_pointer.
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": "Widget",
                "offers": {"@type": "Offer", "priceCurrency": "USD"},
            }
        ],
    }
    result = _validate(payload)
    issues = shacl.extract_validation_issues(result, payload)
    assert issues

    # Every field the SDK hands out is fully resolved and urn-free.
    for issue in issues:
        for field in (issue.focus_node, issue.node_pointer, issue.value, issue.message):
            assert "urn:wl:node:" not in (field or "")
        assert issue.focus_node is None  # all nodes here are anonymous

    # The SDK — not the consumer — resolved the pointers, so the nested Offer is
    # addressable and the constraint component is carried through.
    pointers = {i.node_pointer for i in issues}
    assert "/@graph/0" in pointers
    assert "/@graph/0/offers" in pointers
    assert any(
        (i.constraint_component or "").endswith("MinCountConstraintComponent")
        for i in issues
    )

    # Without source_jsonld there is nothing to resolve against -> node_pointer is
    # None, but findings are still urn-free.
    no_source = shacl.extract_validation_issues(result)
    assert no_source
    assert all(i.node_pointer is None for i in no_source)
    assert all("urn:wl:node:" not in (i.message or "") for i in no_source)

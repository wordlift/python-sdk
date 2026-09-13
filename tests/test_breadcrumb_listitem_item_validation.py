"""Google lets the *last* breadcrumb entry omit ``item``; every other entry must
carry it.

https://developers.google.com/search/docs/appearance/structured-data/breadcrumb
"""

from rdflib import URIRef
from rdflib.namespace import SH

from wordlift_sdk.validation.shacl import (
    PreparedShaclValidator,
    _load_graph_from_jsonld,
    prepare_shapes,
)

import pytest


@pytest.fixture(scope="module")
def validator() -> PreparedShaclValidator:
    return PreparedShaclValidator(prepare_shapes(["google-breadcrumb"]))


@pytest.fixture(scope="module")
def carousel_validator() -> PreparedShaclValidator:
    return PreparedShaclValidator(prepare_shapes(["google-carousel"]))


@pytest.fixture(scope="module")
def both_validator() -> PreparedShaclValidator:
    return PreparedShaclValidator(
        prepare_shapes(["google-breadcrumb", "google-carousel"])
    )


def _list_item(position: object, item: str | None = None) -> dict:
    node: dict = {"@type": "ListItem", "position": position, "name": "X"}
    if item is not None:
        node["item"] = item
    return node


def _breadcrumb(elements: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": elements,
    }


def _validate(validator: PreparedShaclValidator, elements: list[dict]):
    graph = _load_graph_from_jsonld(_breadcrumb(elements))
    return validator.validate_graph(graph)


def _conforms(validator: PreparedShaclValidator, elements: list[dict]) -> bool:
    return _validate(validator, elements).conforms


A = "https://example.com/a"
B = "https://example.com/b"
C = "https://example.com/c"


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param(
            [_list_item(1, A), _list_item(2, B)],
            id="every-entry-has-item",
        ),
        pytest.param(
            [_list_item(1, A), _list_item(2)],
            id="final-entry-omits-item",
        ),
        pytest.param([_list_item(1)], id="single-entry-omits-item"),
        # "Last" is the highest ``position``, not the last one written down.
        pytest.param(
            [_list_item(2), _list_item(1, A)],
            id="highest-position-declared-first",
        ),
        # Real-world markup types `position` inconsistently; positions are
        # compared numerically, so these all behave like 1, 2.
        pytest.param(
            [_list_item("1", A), _list_item("2")],
            id="string-positions-final-omits-item",
        ),
        pytest.param(
            [_list_item(1.0, A), _list_item(2.0)],
            id="float-positions-final-omits-item",
        ),
        pytest.param(
            [_list_item("1", A), _list_item(2.0, B), _list_item(3)],
            id="mixed-position-types-final-omits-item",
        ),
    ],
)
def test_trail_conforms_when_only_the_last_entry_omits_item(
    validator: PreparedShaclValidator, elements: list[dict]
) -> None:
    assert _conforms(validator, elements)


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param(
            [_list_item(1), _list_item(2, B)],
            id="first-entry-omits-item",
        ),
        pytest.param(
            [_list_item(1, A), _list_item(2), _list_item(3, C)],
            id="middle-entry-omits-item",
        ),
        pytest.param(
            [_list_item(1, A), _list_item(2), _list_item(3)],
            id="two-entries-omit-item",
        ),
        pytest.param(
            [_list_item(1), _list_item(2), _list_item(3)],
            id="no-entry-has-item",
        ),
        pytest.param(
            [_list_item("1"), _list_item("2", B)],
            id="string-positions-first-omits-item",
        ),
        pytest.param(
            [_list_item(1.0), _list_item(2.0, B)],
            id="float-positions-first-omits-item",
        ),
        pytest.param(
            [_list_item("1"), _list_item(2.0, B)],
            id="mixed-position-types-first-omits-item",
        ),
        pytest.param(
            [_list_item(1), _list_item(1)],
            id="tied-positions-both-omit-item",
        ),
        # A tie means there is no single highest position, so neither entry can
        # be the exempt last one.
        pytest.param(
            [_list_item(1), _list_item(1, A)],
            id="tied-positions-one-omits-item",
        ),
        # The entry omitting `item` carries two positions. It must rank against
        # its sibling, never against itself.
        pytest.param(
            [_list_item(1, A), _list_item([1, 5])],
            id="entry-with-two-positions-ties-its-sibling",
        ),
    ],
)
def test_trail_is_reported_when_a_non_final_entry_omits_item(
    validator: PreparedShaclValidator, elements: list[dict]
) -> None:
    assert not _conforms(validator, elements)


def test_violation_is_an_error_not_a_warning(
    validator: PreparedShaclValidator,
) -> None:
    result = _validate(validator, [_list_item(1), _list_item(2, B)])
    assert not result.conforms
    assert result.warning_count == 0
    assert "sh:Violation" in result.report_text


def test_missing_position_is_still_reported(
    validator: PreparedShaclValidator,
) -> None:
    graph = _load_graph_from_jsonld(_breadcrumb([{"@type": "ListItem", "name": "X"}]))
    result = validator.validate_graph(graph)
    assert not result.conforms
    assert "position" in result.report_text


def _carousel(elements: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": elements,
    }


def _carousel_entry(position: int, url: str, with_item: bool = True) -> dict:
    node: dict = {"@type": "ListItem", "position": position, "url": url}
    if with_item:
        node["item"] = {"@type": "Movie", "name": "M", "url": url}
    return node


def test_carousel_still_requires_item_on_every_entry(
    carousel_validator: PreparedShaclValidator,
) -> None:
    complete = _carousel([_carousel_entry(1, A), _carousel_entry(2, B)])
    assert carousel_validator.validate_graph(_load_graph_from_jsonld(complete)).conforms

    last_omits_item = _carousel(
        [_carousel_entry(1, A), _carousel_entry(2, B, with_item=False)]
    )
    assert not carousel_validator.validate_graph(
        _load_graph_from_jsonld(last_omits_item)
    ).conforms


def test_breadcrumb_rule_does_not_leak_into_carousels(
    both_validator: PreparedShaclValidator,
) -> None:
    """Loading both shapes together must not swap their verdicts. The carousel
    verdict on its own is covered above.

    Scope is the bare data graph. A graph that *also* asserts
    `BreadcrumbList rdfs:subClassOf ItemList` still loses the exemption under
    `inference="rdfs"`, because the entailed `rdf:type ItemList` hands the trail
    to the carousel shape. That predates this constraint and is not covered here.
    """
    breadcrumb = _breadcrumb([_list_item(1, A), _list_item(2)])
    assert both_validator.validate_graph(_load_graph_from_jsonld(breadcrumb)).conforms

    carousel = _carousel(
        [_carousel_entry(1, A), _carousel_entry(2, B, with_item=False)]
    )
    assert not both_validator.validate_graph(_load_graph_from_jsonld(carousel)).conforms


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param([_list_item("9", A), _list_item("10")], id="string-9-then-10"),
        pytest.param(
            [_list_item(str(i), A) for i in range(1, 10)] + [_list_item("10")],
            id="string-1-to-10",
        ),
        pytest.param([_list_item(9, A), _list_item(10)], id="int-9-then-10"),
    ],
)
def test_multi_digit_positions_are_ordered_numerically(
    validator: PreparedShaclValidator, elements: list[dict]
) -> None:
    """The final entry omits `item`, so these must conform. Ordering positions
    lexicographically would rank "9" after "10" and reject them."""
    assert _conforms(validator, elements)


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param(
            [_list_item(-3, A), _list_item(-2), _list_item(-1, A)],
            id="negative-positions",
        ),
        pytest.param(
            [_list_item(" 1", A), _list_item(" 2"), _list_item(" 3", A)],
            id="whitespace-padded-positions",
        ),
        pytest.param(
            [_list_item("01", A), _list_item("02"), _list_item("03", A)],
            id="zero-padded-positions",
        ),
        pytest.param(
            [_list_item(0, A), _list_item(1), _list_item(2, A)],
            id="zero-indexed-positions",
        ),
    ],
)
def test_signed_and_padded_positions_are_still_ranked(
    validator: PreparedShaclValidator, elements: list[dict]
) -> None:
    """A numeric guard narrower than the xsd:double cast would drop the sign or
    the padding and silently exempt these."""
    assert not _conforms(validator, elements)


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param(
            [_list_item("a", A), _list_item("b"), _list_item("c", A)],
            id="non-numeric-positions",
        ),
        # "NaN" reaches the same place by a different route than "a"/"b"/"c":
        # it *is* a valid xsd:double lexical form, so the cast succeeds rather
        # than raising, and NaN then loses every comparison.
        pytest.param(
            [_list_item("NaN"), _list_item(2, A)],
            id="nan-position-omits-item",
        ),
        pytest.param(
            [_list_item("a"), _list_item("b")],
            id="non-numeric-positions-two-omit",
        ),
    ],
)
def test_unrankable_positions_are_reported(
    validator: PreparedShaclValidator, elements: list[dict]
) -> None:
    """A position the order constraint cannot rank is reported as a position, not
    left to exempt the entry beside it. The guard is the same cast, so the set it
    reports is exactly the set that would not rank."""
    result = _validate(validator, elements)
    assert not result.conforms
    assert "position must be a number" in result.report_text


@pytest.mark.parametrize(
    "elements,conforms",
    [
        # -INF is the lowest position, so the entry omitting `item` is first.
        pytest.param([_list_item("-INF"), _list_item(2, A)], False, id="minus-inf"),
        # INF is the highest, so the entry omitting `item` really is last.
        pytest.param([_list_item("INF"), _list_item(2, A)], True, id="inf"),
    ],
)
def test_infinite_positions_rank_as_expected(
    validator: PreparedShaclValidator, elements: list[dict], conforms: bool
) -> None:
    """Unlike NaN, the infinities cast cleanly *and* order, so they are ranked
    rather than exempted."""
    assert _conforms(validator, elements) is conforms


def test_every_result_reports_a_path_the_focus_node_actually_has(
    validator: PreparedShaclValidator,
) -> None:
    """sh:resultPath is a path from sh:focusNode — the BreadcrumbList, not the
    entry. The offending entry travels in sh:value instead."""
    result = _validate(validator, [_list_item(1), _list_item(2), _list_item(3, C)])

    assert not result.conforms
    paths = set(result.report_graph.objects(None, SH.resultPath))
    assert paths == {URIRef("http://schema.org/itemListElement")}


def test_report_text_does_not_repeat_the_sparql_query(
    validator: PreparedShaclValidator,
) -> None:
    """The constraint is named rather than inline so that report_text, which is
    shown to users and fed to the quality agent, does not carry a copy of the
    query per result. See the note in generator.py."""
    result = _validate(validator, [_list_item(1), _list_item(2), _list_item(3, C)])

    assert not result.conforms
    assert "SELECT $this" not in result.report_text
    # A full IRI, not the `:` prefix: the prepared shapes graph merges every
    # shape file and carries no single file's prefix bindings.
    source_constraints = [
        line.strip()
        for line in result.report_text.splitlines()
        if "Source Constraint:" in line
    ]
    assert source_constraints
    assert all(
        line.endswith("google_BreadcrumbListItemOrderConstraint>")
        for line in source_constraints
    )


def test_each_offending_entry_is_reported_once(
    validator: PreparedShaclValidator,
) -> None:
    """Positions 2 and 3 both omit `item`; only position 2 is wrong. Naming
    position 3 would tell the quality agent that consumes report_text to add
    `item` to the one crumb Google exempts."""
    result = _validate(validator, [_list_item(1, A), _list_item(2), _list_item(3)])

    assert not result.conforms
    # report_graph keeps the internal urn:wl:node: ids; only report_text is scrubbed.
    values = sorted(
        str(v).removeprefix("urn:wl:node:")
        for v in result.report_graph.objects(None, SH.value)
    )
    assert values == ["/itemListElement/1"]

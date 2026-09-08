from wordlift_sdk.validation.shacl import (
    PreparedShaclValidator,
    _load_graph_from_jsonld,
    prepare_shapes,
)

import pytest


@pytest.fixture(scope="module")
def validator() -> PreparedShaclValidator:
    return PreparedShaclValidator(prepare_shapes(["google-breadcrumb"]))


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


def _conforms(validator: PreparedShaclValidator, elements: list[dict]) -> bool:
    graph = _load_graph_from_jsonld(_breadcrumb(elements))
    return validator.validate_graph(graph).conforms


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param(
            [
                _list_item(1, "https://example.com/a"),
                _list_item(2, "https://example.com/b"),
            ],
            id="every-entry-has-item",
        ),
        pytest.param(
            [_list_item(1, "https://example.com/a"), _list_item(2)],
            id="final-entry-omits-item",
        ),
        pytest.param(
            [_list_item(1), _list_item(2, "https://example.com/b")],
            id="first-entry-omits-item",
        ),
        pytest.param([_list_item(1)], id="single-entry-omits-item"),
    ],
)
def test_one_entry_may_omit_item(
    validator: PreparedShaclValidator, elements: list[dict]
) -> None:
    assert _conforms(validator, elements)


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param(
            [_list_item(1, "https://example.com/a"), _list_item(2), _list_item(3)],
            id="two-entries-omit-item",
        ),
        pytest.param(
            [_list_item(1), _list_item(2), _list_item(3)],
            id="no-entry-has-item",
        ),
        pytest.param(
            [_list_item(1.0), _list_item(2.0), _list_item(3.0)],
            id="float-positions",
        ),
        pytest.param(
            [_list_item("1"), _list_item("2"), _list_item("3")],
            id="string-positions",
        ),
        pytest.param([_list_item(1), _list_item(1)], id="tied-positions"),
    ],
)
def test_two_or_more_entries_omitting_item_fail(
    validator: PreparedShaclValidator, elements: list[dict]
) -> None:
    assert not _conforms(validator, elements)


def test_missing_position_is_still_reported(
    validator: PreparedShaclValidator,
) -> None:
    graph = _load_graph_from_jsonld(_breadcrumb([{"@type": "ListItem", "name": "X"}]))
    result = validator.validate_graph(graph)
    assert not result.conforms
    assert "position" in result.report_text

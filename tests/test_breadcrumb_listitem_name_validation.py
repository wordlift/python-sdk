import json
from pathlib import Path

from wordlift_sdk.validation import shacl
from wordlift_sdk.validation.shacl import extract_validation_issues


def _write_jsonld(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _breadcrumb(list_item: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": 1, **list_item}],
    }


def test_listitem_name_not_required_when_item_is_thing_with_name(
    tmp_path: Path,
) -> None:
    payload = _breadcrumb({"item": {"@id": "https://example.com/", "name": "Home"}})
    path = _write_jsonld(tmp_path, "listitem-item-name.jsonld", payload)

    result = shacl.validate_file(path.as_posix(), shape_specs=["google-breadcrumb"])

    assert result.conforms is True, result.report_text


def test_listitem_name_required_when_item_is_bare_url(tmp_path: Path) -> None:
    payload = _breadcrumb({"item": "https://example.com/"})
    path = _write_jsonld(tmp_path, "listitem-bare-url-no-name.jsonld", payload)

    result = shacl.validate_file(path.as_posix(), shape_specs=["google-breadcrumb"])

    assert result.conforms is False
    assert any(
        "OrConstraintComponent" in issue.constraint_component
        for issue in extract_validation_issues(result)
    )


def test_listitem_name_required_when_item_is_thing_without_name(
    tmp_path: Path,
) -> None:
    payload = _breadcrumb({"item": {"@id": "https://example.com/"}})
    path = _write_jsonld(tmp_path, "listitem-item-without-name.jsonld", payload)

    result = shacl.validate_file(path.as_posix(), shape_specs=["google-breadcrumb"])

    assert result.conforms is False
    assert any(
        "OrConstraintComponent" in issue.constraint_component
        for issue in extract_validation_issues(result)
    )


def test_listitem_top_level_name_satisfies_requirement_with_bare_url_item(
    tmp_path: Path,
) -> None:
    payload = _breadcrumb({"item": "https://example.com/", "name": "Home"})
    path = _write_jsonld(tmp_path, "listitem-name-and-bare-url.jsonld", payload)

    result = shacl.validate_file(path.as_posix(), shape_specs=["google-breadcrumb"])

    assert result.conforms is True, result.report_text

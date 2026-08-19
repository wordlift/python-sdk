import json
from pathlib import Path

from wordlift_sdk.validation import shacl
from wordlift_sdk.validation.shacl import extract_validation_issues


def _write_jsonld(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _range_check_messages(result) -> list[str]:
    return [
        issue.message
        for issue in extract_validation_issues(result)
        if issue.message.startswith("Schema.org range check:")
    ]


def test_breadcrumb_listitem_item_without_type_has_no_range_check_warning(
    tmp_path: Path,
) -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "item": {"@id": "https://example.com/", "name": "Home"},
            }
        ],
    }
    path = _write_jsonld(tmp_path, "breadcrumb-untyped-item.jsonld", payload)

    result = shacl.validate_file(
        path.as_posix(), shape_specs=["google-breadcrumb", "schemaorg-grammar"]
    )

    assert result.conforms is True, result.report_text
    assert _range_check_messages(result) == []


def test_review_item_reviewed_without_type_has_no_range_check_warning(
    tmp_path: Path,
) -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "Review",
        "reviewBody": "Great product.",
        "itemReviewed": {"@id": "https://example.com/product"},
    }
    path = _write_jsonld(tmp_path, "review-untyped-item-reviewed.jsonld", payload)

    result = shacl.validate_file(path.as_posix(), shape_specs=["schemaorg-grammar"])

    assert "Schema.org range check: itemReviewed." not in _range_check_messages(result)

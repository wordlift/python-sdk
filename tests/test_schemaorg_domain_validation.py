from __future__ import annotations

import json
from pathlib import Path

import pytest

from wordlift_sdk.validation import shacl


_MESSAGE = (
    "The property isPartOf is not recognized by the schema (e.g. schema.org) "
    "for an object of type Service."
)


def _validate_payload(tmp_path: Path, types: str | list[str]):
    path = tmp_path / "schemaorg-domain.jsonld"
    path.write_text(
        json.dumps(
            {
                "@context": {"@vocab": "https://schema.org/"},
                "@id": "https://example.org/items/1",
                "@type": types,
                "isPartOf": {"@id": "https://example.org/site"},
            }
        ),
        encoding="utf-8",
    )
    return shacl.validate_file(path.as_posix(), shape_specs=["schemaorg-grammar"])


def _domain_issues(result):
    return [
        issue
        for issue in shacl.extract_validation_issues(result)
        if "is not recognized by the schema" in issue.message
    ]


def test_schemaorg_domain_rejects_is_part_of_on_service(tmp_path: Path) -> None:
    result = _validate_payload(tmp_path, "Service")
    issues = _domain_issues(result)

    assert len(issues) == 1
    assert result.warning_count == 1
    assert _MESSAGE in result.report_text
    assert issues[0].level == "warning"
    assert issues[0].focus_node == "https://example.org/items/1"
    assert issues[0].result_path == "http://schema.org/isPartOf"
    assert issues[0].rule_set == "schemaorg-grammar"
    assert issues[0].message == _MESSAGE


@pytest.mark.parametrize(
    "types",
    ["CreativeWork", "Article", ["Service", "CreativeWork"]],
)
def test_schemaorg_domain_accepts_compatible_type_or_subtype(
    tmp_path: Path,
    types: str | list[str],
) -> None:
    assert _domain_issues(_validate_payload(tmp_path, types)) == []


def test_schemaorg_domain_reports_unrelated_multitype_once(tmp_path: Path) -> None:
    issues = _domain_issues(_validate_payload(tmp_path, ["Service", "Product"]))

    assert len(issues) == 1


def test_schemaorg_domain_ignores_untyped_and_external_predicates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "domain-boundaries.jsonld"
    path.write_text(
        json.dumps(
            {
                "@context": {"@vocab": "http://schema.org/"},
                "@graph": [
                    {
                        "@id": "https://example.org/untyped",
                        "isPartOf": "https://example.org/site",
                    },
                    {
                        "@id": "https://example.org/service",
                        "@type": "Service",
                        "https://example.org/isPartOf": "https://example.org/site",
                        "name": "Valid inherited Thing property",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = shacl.validate_file(
        path.as_posix(),
        shape_specs=["schemaorg-grammar"],
    )
    assert _domain_issues(result) == []

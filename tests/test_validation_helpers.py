from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SH

from wordlift_sdk.validation import shacl


def _validation_result() -> shacl.ValidationResult:
    report_graph = Graph()
    violation = URIRef("urn:result:violation")
    warning = URIRef("urn:result:warning")
    violation_shape = URIRef("urn:shape:headline")
    warning_shape = URIRef("urn:shape:image")
    focus = URIRef("https://example.com/article#post")
    report_graph.add((violation, SH.resultSeverity, SH.Violation))
    report_graph.add((violation, SH.sourceShape, violation_shape))
    report_graph.add((violation, SH.focusNode, focus))
    report_graph.add((violation, SH.resultPath, URIRef("http://schema.org/headline")))
    report_graph.add((violation, SH.resultMessage, Literal("Missing headline")))
    report_graph.add((warning, SH.resultSeverity, SH.Warning))
    report_graph.add((warning, SH.sourceShape, warning_shape))
    report_graph.add((warning, SH.focusNode, focus))
    report_graph.add((warning, SH.resultPath, URIRef("http://schema.org/image")))
    report_graph.add((warning, SH.resultMessage, Literal("Image type is broad")))
    return shacl.ValidationResult(
        conforms=False,
        report_text="report",
        report_graph=report_graph,
        data_graph=Graph(),
        shape_source_map={
            violation_shape: "google-article",
            warning_shape: "schemaorg-grammar",
        },
        warning_count=1,
    )


def test_resolve_shape_specs_include_exclude_and_extra(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        shacl, "_shape_resource_names", lambda: ["google-article.ttl", "schemaorg.ttl"]
    )
    custom = tmp_path / "custom.ttl"
    custom.write_text("", encoding="utf-8")
    specs = shacl.resolve_shape_specs(
        builtin_shapes=["google-article"],
        exclude_builtin_shapes=["google-article"],
        extra_shapes=[custom.as_posix()],
    )
    assert specs == [custom.as_posix()]


def test_resolve_shape_specs_unknown_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shacl, "_shape_resource_names", lambda: ["google-article.ttl"])
    with pytest.raises(RuntimeError, match="Unknown builtin shape value"):
        shacl.resolve_shape_specs(builtin_shapes=["missing"])


def test_resolve_shape_specs_default_excludes_opt_in_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shacl,
        "_shape_resource_names",
        lambda: ["google-article.ttl", "google-image-license-metadata.ttl"],
    )
    specs = shacl.resolve_shape_specs()
    assert specs == ["google-article.ttl"]


def test_resolve_shape_specs_can_explicitly_include_opt_in_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shacl,
        "_shape_resource_names",
        lambda: ["google-article.ttl", "google-image-license-metadata.ttl"],
    )
    specs = shacl.resolve_shape_specs(builtin_shapes=["google-image-license-metadata"])
    assert specs == ["google-image-license-metadata.ttl"]


def test_resolve_shape_sources_default_excludes_opt_in_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shacl,
        "_shape_resource_names",
        lambda: ["google-article.ttl", "google-image-license-metadata.ttl"],
    )
    assert shacl._resolve_shape_sources(None) == ["google-article.ttl"]


def test_extract_and_filter_issues() -> None:
    issues = shacl.extract_validation_issues(_validation_result())
    assert len(issues) == 2
    assert {issue.level for issue in issues} == {"error", "warning"}
    error_issues = shacl.filter_validation_issues(issues, "error")
    assert len(error_issues) == 1
    assert error_issues[0].rule_id == "urn:shape:headline"
    assert error_issues[0].rule_set == "google-article"

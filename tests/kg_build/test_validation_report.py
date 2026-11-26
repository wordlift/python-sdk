from __future__ import annotations

import csv
import time
from pathlib import Path

from rdflib import Graph

from wordlift_sdk.kg_build.validation_report import (
    CSV_HEADER,
    STATIC_TEMPLATES_LABEL,
    ValidationReportWriter,
)
from wordlift_sdk.validation import shacl_validation_service as service
from wordlift_sdk.validation.shacl_validation_service import (
    MAX_ERROR_DETAILS_PER_GRAPH,
    ValidationErrorDetail,
    ValidationOutcome,
)

_EVENT_SHAPE = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix schema: <http://schema.org/> .
@prefix ex: <https://example.com/shapes/> .

ex:EventShape a sh:NodeShape ;
  sh:targetClass schema:Event ;
  sh:property [ sh:path schema:name ; sh:minCount 1 ] ;
  sh:property [ sh:path ( schema:location schema:address ) ; sh:minCount 1 ] .
"""


def _detail(
    rule_id: str, path: str | None = None, focus: str = "f"
) -> ValidationErrorDetail:
    return ValidationErrorDetail(
        rule_set="google-product-snippet",
        rule_id=f"https://wordlift.io/shacl/google/product-snippet/{rule_id}",
        path=path,
        focus_node=focus,
        value=None,
        message=f"{rule_id} message",
    )


def _outcome(
    *errors: ValidationErrorDetail, error_count: int | None = None
) -> ValidationOutcome:
    count = len(errors) if error_count is None else error_count
    return ValidationOutcome(
        passed=count == 0,
        warning_sources={"google-organization": 3},
        error_sources={"google-product-snippet": count} if count else {},
        queue_wait_ms=0,
        validation_ms=0,
        errors=list(errors),
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _validate(graph_turtle: str, shape_specs: list[str]) -> dict:
    service._init_worker(shape_specs)
    graph = Graph()
    graph.parse(data=graph_turtle, format="turtle")
    return service._validate_in_worker(graph.serialize(format="nt"), time.time())


def test_worker_returns_error_details_for_named_and_anonymous_shapes(
    tmp_path: Path,
) -> None:
    shape = tmp_path / "event_shape.ttl"
    shape.write_text(_EVENT_SHAPE, encoding="utf-8")

    result = _validate(
        """
        @prefix schema: <http://schema.org/> .
        <https://data.example.com/r1> a schema:Review ;
            schema:author <https://data.example.com/a1> .
        <https://data.example.com/e1> a schema:Event ;
            schema:location <https://data.example.com/l1> .
        <https://data.example.com/l1> a schema:Place .
        """,
        ["google-review-snippet", str(shape)],
    )

    errors = {(e["rule_set"], e["rule_id"], e["path"]): e for e in result["errors"]}
    # Anonymous property shapes take the id of the named shape that holds them;
    # the result path tells them apart, sequence paths included.
    assert ("event_shape", "https://example.com/shapes/EventShape", "name") in errors
    assert (
        "event_shape",
        "https://example.com/shapes/EventShape",
        "location.address",
    ) in errors
    review = errors[
        (
            "google-review-snippet",
            "https://wordlift.io/shacl/google/review-snippet/review-itemreviewed-required",
            None,
        )
    ]
    assert review["focus_node"] == "https://data.example.com/r1"
    assert "standalone Review must have itemReviewed" in review["message"]
    # Details cover errors only; their count matches the per-source counts.
    assert len(result["errors"]) == sum(result["error_sources"].values())
    assert result["warning_sources"]


def test_worker_caps_error_details_but_not_counts(tmp_path: Path) -> None:
    shape = tmp_path / "event_shape.ttl"
    shape.write_text(_EVENT_SHAPE, encoding="utf-8")
    events = "\n".join(
        f"<https://data.example.com/e{i}> a schema:Event ."
        for i in range(MAX_ERROR_DETAILS_PER_GRAPH)
    )

    result = _validate(
        "@prefix schema: <http://schema.org/> .\n" + events, [str(shape)]
    )

    assert result["error_sources"] == {"event_shape": 2 * MAX_ERROR_DETAILS_PER_GRAPH}
    assert len(result["errors"]) == MAX_ERROR_DETAILS_PER_GRAPH
    keys = [
        (e["rule_set"], e["rule_id"], e["path"], e["focus_node"])
        for e in result["errors"]
    ]
    assert keys == sorted(keys)


def test_writer_writes_header_even_without_errors(tmp_path: Path) -> None:
    path = tmp_path / "out" / "graph_sync_validation.csv"
    writer = ValidationReportWriter(path)
    writer.record("https://example.com/ok", _outcome())

    with path.open(newline="", encoding="utf-8") as fh:
        assert next(csv.reader(fh)) == list(CSV_HEADER)
    assert _rows(path) == []
    markdown = writer.render_markdown()
    assert "| Pages validated | **1** |" in markdown
    assert "| Pages with errors | **0** |" in markdown
    assert "Top errors" not in markdown


def test_writer_streams_one_row_per_error(tmp_path: Path) -> None:
    path = tmp_path / "graph_sync_validation.csv"
    writer = ValidationReportWriter(path)

    writer.record(
        "https://example.com/p1",
        _outcome(
            _detail("offer-price-required", "offers.price"), _detail("name-required")
        ),
    )
    # Rows are on disk as soon as a page is recorded, not at the end of the run.
    assert len(_rows(path)) == 2

    writer.record(
        STATIC_TEMPLATES_LABEL, _outcome(_detail("name-required", focus="org"))
    )
    rows = _rows(path)
    assert [r["url"] for r in rows] == [
        "https://example.com/p1",
        "https://example.com/p1",
        STATIC_TEMPLATES_LABEL,
    ]
    assert rows[0] == {
        "url": "https://example.com/p1",
        "severity": "error",
        "rule_set": "google-product-snippet",
        "rule_id": "https://wordlift.io/shacl/google/product-snippet/offer-price-required",
        "path": "offers.price",
        "focus_node": "f",
        "value": "",
        "message": "offer-price-required message",
    }


def test_writer_ranks_rules_by_pages_affected(tmp_path: Path) -> None:
    writer = ValidationReportWriter(tmp_path / "graph_sync_validation.csv")
    # One page with many errors of a rule must not outrank a rule on more pages.
    writer.record(
        "https://example.com/p1",
        _outcome(
            *[
                _detail("offer-price-required", "offers.price", f"o{i}")
                for i in range(5)
            ]
        ),
    )
    writer.record("https://example.com/p2", _outcome(_detail("name-required")))
    writer.record("https://example.com/p3", _outcome(_detail("name-required")))
    writer.record("https://example.com/p4", _outcome())

    markdown = writer.render_markdown()

    assert "| Pages validated | **4** |" in markdown
    assert "| Pages with errors | **3** |" in markdown
    assert "| Errors | **7** |" in markdown
    table = markdown.split("### Top errors by pages affected", 1)[1]
    name_row, price_row = [
        line
        for line in table.splitlines()
        if line.startswith("| 2") or line.startswith("| 1")
    ]
    assert name_row.startswith(
        "| 2 | 2 | `google-product-snippet` | `name-required` | `-` |"
    )
    assert "[https://example.com/p2](https://example.com/p2)" in name_row
    assert price_row.startswith(
        "| 1 | 5 | `google-product-snippet` | `offer-price-required` | `offers.price` |"
    )
    assert "graph_sync_validation.csv" in markdown
    assert "more than" not in markdown


def test_writer_notes_pages_with_omitted_errors(tmp_path: Path) -> None:
    writer = ValidationReportWriter(tmp_path / "graph_sync_validation.csv")
    writer.record(
        "https://example.com/p1",
        _outcome(_detail("name-required"), error_count=MAX_ERROR_DETAILS_PER_GRAPH + 5),
    )

    markdown = writer.render_markdown()

    assert f"| Errors | **{MAX_ERROR_DETAILS_PER_GRAPH + 5}** |" in markdown
    assert f"1 page(s) had more than {MAX_ERROR_DETAILS_PER_GRAPH} errors" in markdown


def test_writer_lists_at_most_ten_rules(tmp_path: Path) -> None:
    writer = ValidationReportWriter(tmp_path / "graph_sync_validation.csv")
    writer.record(
        "https://example.com/p1",
        _outcome(*[_detail(f"rule-{i:02d}") for i in range(12)]),
    )

    markdown = writer.render_markdown()

    assert "`rule-09`" in markdown
    assert "`rule-10`" not in markdown
    assert "…and 2 more rule(s)." in markdown

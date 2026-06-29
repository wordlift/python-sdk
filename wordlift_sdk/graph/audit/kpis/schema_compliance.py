"""KPI: SHACL schema compliance aggregated by webpage URL."""

from __future__ import annotations

from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal as TypingLiteral

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import SH

from .rich_snippets import (
    RichSnippetsValidationSummary,
    build_rich_snippets_validation_summary,
)
from wordlift_sdk.validation.shacl import (
    _normalize_schema_org_uris,  # type: ignore[attr-defined]
    PreparedShaclValidator,
    _should_skip_schemaorg_subclass_range_warning,  # type: ignore[attr-defined]
)

_SCHEMA_URL_HTTP = URIRef("http://schema.org/url")
_SCHEMA_URL_HTTPS = URIRef("https://schema.org/url")
_MERCHANT_SHAPE = "google-merchant-listing.ttl"


@dataclass
class IssueEntry:
    severity: str
    message: str
    focus_node: str | None = None
    path: str | None = None
    source_shape: str | None = None
    shape_source: str | None = None
    constraint_component: str | None = None
    value: str | None = None
    code: str | None = None
    position: int | None = None

    def to_dict(self) -> dict:
        data: dict = {"severity": self.severity, "message": self.message}
        for attr in (
            "focus_node",
            "path",
            "source_shape",
            "shape_source",
            "constraint_component",
            "value",
            "code",
            "position",
        ):
            value = getattr(self, attr)
            if value is not None:
                data[attr] = value
        return data


@dataclass
class MerchantResult:
    errors: list[IssueEntry]
    warnings: list[IssueEntry]
    eligible: bool

    def to_dict(self) -> dict:
        return {
            "errors": [entry.to_dict() for entry in self.errors],
            "warnings": [entry.to_dict() for entry in self.warnings],
            "eligible": self.eligible,
        }


@dataclass
class UrlComplianceResult:
    url: str
    errors: list[IssueEntry]
    warnings: list[IssueEntry]
    error_count: int
    warning_count: int
    google_merchant: MerchantResult

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "errors": [entry.to_dict() for entry in self.errors],
            "warnings": [entry.to_dict() for entry in self.warnings],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "google_merchant": self.google_merchant.to_dict(),
        }


@dataclass(frozen=True)
class SchemaComplianceResult:
    by_url: list[UrlComplianceResult]

    def to_dict(self) -> dict:
        return {"schema_compliance": [result.to_dict() for result in self.by_url]}


@dataclass(frozen=True)
class SchemaComplianceRun:
    schema_compliance: SchemaComplianceResult
    rich_snippets: RichSnippetsValidationSummary


@dataclass(frozen=True)
class ExtractedIssues:
    errors: list[IssueEntry]
    warnings: list[IssueEntry]
    error_count: int
    warning_count: int


class SchemaComplianceKpi:
    """
    Run SHACL validation per webpage-URL subgraph.

    Subgraph assembly for each webpage URL:
    1. Root IRIs: subjects whose schema:url = the webpage URL.
    2. IRI-prefix children: subjects whose IRI starts with ``{root_iri}/``.
    3. Referenced entities (``depth`` hops): follow object-property edges
       where the object is also a known subject in the graph.
    4. Blank nodes are excluded.

    Merchant-listing shape runs separately and is reported under
    ``google_merchant``.

    Prepared validators are kept on the KPI instance so shape loading and shape
    harvest are paid once and reused across calls.
    """

    def __init__(
        self,
        shape_specs: list[str],
        depth: int = 1,
        issue_level: TypingLiteral["warning", "error"] = "warning",
        max_workers: int | None = None,
        include_issue_details: bool = True,
    ) -> None:
        self._depth = depth
        self._issue_level = issue_level
        self._max_workers = max_workers
        self._include_issue_details = include_issue_details
        self._last_run: SchemaComplianceRun | None = None

        merchant_specs = [
            spec for spec in shape_specs if spec.endswith(_MERCHANT_SHAPE)
        ]
        main_specs = [
            spec for spec in shape_specs if not spec.endswith(_MERCHANT_SHAPE)
        ]
        self._main_validator = PreparedShaclValidator.from_shape_specs(main_specs)
        self._merchant_validator = PreparedShaclValidator.from_shape_specs(
            merchant_specs
        )

    def collect(self, graph: Graph) -> SchemaComplianceResult:
        normalized = _normalize_schema_org_uris(graph)
        webpage_urls = _find_webpage_urls(normalized)
        if not webpage_urls:
            self._last_run = SchemaComplianceRun(
                schema_compliance=SchemaComplianceResult(by_url=[]),
                rich_snippets=RichSnippetsValidationSummary(
                    entity_types={},
                    invalid_entities=frozenset(),
                ),
            )
            return self._last_run.schema_compliance

        all_subjects = {
            subject for subject in normalized.subjects() if isinstance(subject, URIRef)
        }
        subject_index = _build_subject_index(all_subjects)
        subgraphs = {
            url: _build_subgraph(
                normalized, url, self._depth, all_subjects, subject_index
            )
            for url in webpage_urls
        }
        return self.collect_prebuilt(subgraphs)

    def collect_prebuilt(
        self, subgraphs_by_url: dict[str, Graph]
    ) -> SchemaComplianceResult:
        run = self.run_prebuilt(subgraphs_by_url)
        return run.schema_compliance

    def run_prebuilt(self, subgraphs_by_url: dict[str, Graph]) -> SchemaComplianceRun:
        rich_entity_types: dict[str, set[str]] = {}
        rich_invalid_entities: set[str] = set()

        items = sorted(subgraphs_by_url.items())
        if self._max_workers == 1 or len(items) <= 1:
            collected = [
                self._validate_url_subgraph(url, graph) for url, graph in items
            ]
        else:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                collected = list(
                    executor.map(lambda item: self._validate_url_subgraph(*item), items)
                )

        results: list[UrlComplianceResult] = []
        for result, rich_summary in collected:
            results.append(result)
            for iri, types in rich_summary.entity_types.items():
                rich_entity_types.setdefault(iri, set()).update(types)
            rich_invalid_entities.update(rich_summary.invalid_entities)

        self._last_run = SchemaComplianceRun(
            schema_compliance=SchemaComplianceResult(by_url=results),
            rich_snippets=RichSnippetsValidationSummary(
                entity_types={
                    iri: tuple(sorted(types))
                    for iri, types in sorted(rich_entity_types.items())
                },
                invalid_entities=frozenset(rich_invalid_entities),
            ),
        )
        return self._last_run

    def _validate_url_subgraph(
        self,
        url: str,
        subgraph: Graph,
    ) -> tuple[UrlComplianceResult, RichSnippetsValidationSummary]:
        main_validation = self._main_validator.validate_graph(
            subgraph, normalize_schema_org=False
        )
        merchant_validation = self._merchant_validator.validate_graph(
            subgraph, normalize_schema_org=False
        )

        main_issues = _extract_issues(
            main_validation.report_graph,
            self._main_validator.prepared_shapes.shape_source_map,
            data_graph=subgraph,
            shapes_graph=self._main_validator.prepared_shapes.shapes_graph,
            issue_level=self._issue_level,
            include_issue_details=self._include_issue_details,
        )
        merchant_issues = _extract_issues(
            merchant_validation.report_graph,
            self._merchant_validator.prepared_shapes.shape_source_map,
            data_graph=subgraph,
            shapes_graph=self._merchant_validator.prepared_shapes.shapes_graph,
            issue_level=self._issue_level,
            include_issue_details=self._include_issue_details,
        )

        rich_summary = build_rich_snippets_validation_summary(
            subgraph,
            main_validation.report_graph,
            self._main_validator.prepared_shapes.shape_source_map,
        )
        return (
            UrlComplianceResult(
                url=url,
                errors=main_issues.errors,
                warnings=main_issues.warnings,
                error_count=main_issues.error_count,
                warning_count=main_issues.warning_count,
                google_merchant=MerchantResult(
                    errors=merchant_issues.errors,
                    warnings=merchant_issues.warnings,
                    eligible=merchant_issues.error_count == 0,
                ),
            ),
            rich_summary,
        )

    @property
    def last_run(self) -> SchemaComplianceRun | None:
        return self._last_run


def _find_webpage_urls(graph: Graph) -> set[str]:
    urls: set[str] = set()
    for predicate in (_SCHEMA_URL_HTTP, _SCHEMA_URL_HTTPS):
        for _, _, obj in graph.triples((None, predicate, None)):
            if isinstance(obj, (URIRef, Literal)):
                urls.add(str(obj))
    return urls


def _build_subgraph(
    graph: Graph,
    webpage_url: str,
    depth: int,
    all_subjects: set[URIRef],
    subject_index: tuple[list[str], dict[str, URIRef]] | None = None,
) -> Graph:
    index = subject_index or _build_subject_index(all_subjects)
    root_iris: set[URIRef] = set()
    for predicate in (_SCHEMA_URL_HTTP, _SCHEMA_URL_HTTPS):
        for subject, _, obj in graph.triples((None, predicate, None)):
            if isinstance(subject, URIRef) and str(obj) == webpage_url:
                root_iris.add(subject)

    child_iris: set[URIRef] = set()
    for root_iri in root_iris:
        child_iris.update(_subjects_with_prefix(index, str(root_iri).rstrip("/") + "/"))

    entity_iris: set[URIRef] = root_iris | child_iris
    visited: set[URIRef] = set(entity_iris)
    frontier: set[URIRef] = set(entity_iris)
    for _ in range(depth):
        next_frontier: set[URIRef] = set()
        for iri in frontier:
            for _, _, obj in graph.triples((iri, None, None)):
                if (
                    isinstance(obj, URIRef)
                    and obj in all_subjects
                    and obj not in visited
                ):
                    next_frontier.add(obj)
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break

    for iri in set(visited) - root_iris - child_iris:
        visited.update(_subjects_with_prefix(index, str(iri).rstrip("/") + "/"))

    subgraph = Graph()
    for iri in visited:
        for subject, predicate, obj in graph.triples((iri, None, None)):
            if not isinstance(subject, BNode) and not isinstance(obj, BNode):
                subgraph.add((subject, predicate, obj))
    return subgraph


def _build_subject_index(
    all_subjects: set[URIRef],
) -> tuple[list[str], dict[str, URIRef]]:
    by_value = {str(subject): subject for subject in all_subjects}
    return sorted(by_value), by_value


def _subjects_with_prefix(
    subject_index: tuple[list[str], dict[str, URIRef]],
    prefix: str,
) -> set[URIRef]:
    ordered, by_value = subject_index
    matched: set[URIRef] = set()
    index = bisect_left(ordered, prefix)
    while index < len(ordered):
        value = ordered[index]
        if not value.startswith(prefix):
            break
        matched.add(by_value[value])
        index += 1
    return matched


def _extract_issues(
    report_graph: Graph,
    source_map: dict,
    *,
    data_graph: Graph | None = None,
    shapes_graph: Graph | None = None,
    issue_level: str = "warning",
    include_issue_details: bool = True,
) -> ExtractedIssues:
    errors: list[IssueEntry] = []
    warnings: list[IssueEntry] = []
    error_count = 0
    warning_count = 0

    for node in report_graph.subjects(SH.resultSeverity, None):
        if _should_skip_schemaorg_subclass_range_warning(
            report_graph=report_graph,
            node=node,
            source_map=source_map,
            data_graph=data_graph,
            shapes_graph=shapes_graph,
        ):
            continue
        severity_iri = report_graph.value(node, SH.resultSeverity)
        if severity_iri == SH.Violation:
            error_count += 1
            if include_issue_details:
                errors.append(
                    _build_issue_entry(report_graph, node, source_map, severity_iri)
                )
            continue

        warning_count += 1
        if include_issue_details:
            warnings.append(
                _build_issue_entry(report_graph, node, source_map, severity_iri)
            )

    if issue_level == "error":
        warnings = []
        warning_count = 0

    return ExtractedIssues(
        errors=errors,
        warnings=warnings,
        error_count=error_count,
        warning_count=warning_count,
    )


def _build_issue_entry(
    report_graph: Graph,
    node,
    source_map: dict,
    severity_iri,
) -> IssueEntry:
    source_shape = report_graph.value(node, SH.sourceShape)
    message = report_graph.value(node, SH.resultMessage)
    focus_node = report_graph.value(node, SH.focusNode)
    result_path = report_graph.value(node, SH.resultPath)
    constraint = report_graph.value(node, SH.sourceConstraintComponent)
    value = report_graph.value(node, SH.value)

    severity_label = str(severity_iri).split("#")[-1] if severity_iri else "Violation"
    shape_source = None
    if source_shape is not None:
        shape_source = source_map.get(source_shape) or source_map.get(str(source_shape))

    return IssueEntry(
        severity=severity_label,
        message=str(message) if message is not None else "",
        focus_node=str(focus_node) if focus_node is not None else None,
        path=str(result_path) if result_path is not None else None,
        source_shape=str(source_shape) if source_shape is not None else None,
        shape_source=shape_source,
        constraint_component=str(constraint) if constraint is not None else None,
        value=str(value) if value is not None else None,
    )


def build_subgraph(
    graph: Graph,
    webpage_url: str,
    all_subjects: set[URIRef],
    depth: int = 1,
) -> Graph:
    """
    Build a subgraph for *webpage_url* from *graph*.

    This is the public equivalent of the internal ``_build_subgraph`` helper.
    See :class:`SchemaComplianceKpi` for the full subgraph-assembly rules.
    """
    return _build_subgraph(graph, webpage_url, depth, all_subjects)


__all__ = [
    "ExtractedIssues",
    "IssueEntry",
    "MerchantResult",
    "SchemaComplianceKpi",
    "SchemaComplianceRun",
    "SchemaComplianceResult",
    "UrlComplianceResult",
    "build_subgraph",
]

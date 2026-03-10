"""KPI: SHACL schema compliance aggregated by webpage URL."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Literal as TypingLiteral

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import SH

from wordlift_sdk.validation.shacl import (
    _load_shapes_graph,  # type: ignore[attr-defined]
    _normalize_schema_org_uris,  # type: ignore[attr-defined]
)

_SCHEMA_URL_HTTP = URIRef("http://schema.org/url")
_SCHEMA_URL_HTTPS = URIRef("https://schema.org/url")
_MERCHANT_SHAPE = "google-merchant-listing.ttl"

# Options passed to every Validator instance.
_VALIDATOR_OPTIONS: dict = {
    "inference": "rdfs",
    "abort_on_first": False,
    "allow_infos": True,
    "allow_warnings": True,
}

# ---------------------------------------------------------------------------
# Per-process state (populated by _init_worker in each worker process)
# ---------------------------------------------------------------------------

_main_validator = None
_merchant_validator = None
_main_source_map: dict[str, str] = {}
_merchant_source_map: dict[str, str] = {}


def _init_worker(
    main_shapes_nt: str,
    merchant_shapes_nt: str,
    main_source_map: dict[str, str],
    merchant_source_map: dict[str, str],
) -> None:
    """Initialise one worker process: deserialise shapes and pre-warm validators."""
    global _main_validator, _merchant_validator
    global _main_source_map, _merchant_source_map

    from pyshacl import Validator  # local import — each worker process loads it

    main_shapes = Graph()
    main_shapes.parse(data=main_shapes_nt, format="nt")

    merchant_shapes = Graph()
    merchant_shapes.parse(data=merchant_shapes_nt, format="nt")

    dummy = Graph()

    _main_validator = Validator(
        dummy, shacl_graph=main_shapes, options=dict(_VALIDATOR_OPTIONS)
    )
    # Trigger the shapes-cache build once so every subsequent run() skips it.
    _ = _main_validator.shacl_graph.shapes

    _merchant_validator = Validator(
        dummy, shacl_graph=merchant_shapes, options=dict(_VALIDATOR_OPTIONS)
    )
    _ = _merchant_validator.shacl_graph.shapes

    _main_source_map = main_source_map
    _merchant_source_map = merchant_source_map


def _validate_url_worker(
    args: tuple[str, str, str],
) -> UrlComplianceResult:
    """
    Worker entry-point: validate one subgraph (serialised as N-Triples).

    Uses the pre-warmed per-process Validator instances so shape harvest runs
    only once per worker process, not once per URL.
    """
    url, subgraph_nt, issue_level = args

    subgraph = Graph()
    if subgraph_nt:
        subgraph.parse(data=subgraph_nt, format="nt")

    errors, warnings = _run_with_validator(
        _main_validator, subgraph, _main_source_map, issue_level
    )
    m_errors, m_warnings = _run_with_validator(
        _merchant_validator, subgraph, _merchant_source_map, issue_level
    )

    return UrlComplianceResult(
        url=url,
        errors=errors,
        warnings=warnings,
        error_count=len(errors),
        warning_count=len(warnings),
        google_merchant=MerchantResult(
            errors=m_errors,
            warnings=m_warnings,
            eligible=len(m_errors) == 0,
        ),
    )


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


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
        d: dict = {"severity": self.severity, "message": self.message}
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
            v = getattr(self, attr)
            if v is not None:
                d[attr] = v
        return d


@dataclass
class MerchantResult:
    errors: list[IssueEntry]
    warnings: list[IssueEntry]
    eligible: bool

    def to_dict(self) -> dict:
        return {
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
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
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "google_merchant": self.google_merchant.to_dict(),
        }


@dataclass(frozen=True)
class SchemaComplianceResult:
    by_url: list[UrlComplianceResult]

    def to_dict(self) -> dict:
        return {"schema_compliance": [r.to_dict() for r in self.by_url]}


# ---------------------------------------------------------------------------
# KPI collector
# ---------------------------------------------------------------------------


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

    Performance: subgraphs are built in the calling process, then distributed
    to a ``ProcessPoolExecutor``.  Each worker process deserialises the shapes
    once and pre-warms a ``pyshacl.Validator`` so the shapes-cache harvest is
    paid only once per worker, not once per URL.
    """

    def __init__(
        self,
        shape_specs: list[str],
        depth: int = 1,
        issue_level: TypingLiteral["warning", "error"] = "warning",
        max_workers: int | None = None,
    ) -> None:
        self._depth = depth
        self._issue_level = issue_level
        self._max_workers = max_workers

        merchant_specs = [s for s in shape_specs if s.endswith(_MERCHANT_SHAPE)]
        main_specs = [s for s in shape_specs if not s.endswith(_MERCHANT_SHAPE)]

        main_graph, main_source_map = _load_shapes_graph(main_specs)
        merchant_graph, merchant_source_map = _load_shapes_graph(merchant_specs)

        # Serialise to N-Triples for safe cross-process transfer.
        self._main_shapes_nt: str = main_graph.serialize(format="nt")
        self._merchant_shapes_nt: str = merchant_graph.serialize(format="nt")

        # source_map keys are rdflib Identifiers — stringify for pickling.
        self._main_source_map: dict[str, str] = {
            str(k): v for k, v in main_source_map.items()
        }
        self._merchant_source_map: dict[str, str] = {
            str(k): v for k, v in merchant_source_map.items()
        }

    def collect(self, graph: Graph) -> SchemaComplianceResult:
        normalized = _normalize_schema_org_uris(graph)
        webpage_urls = _find_webpage_urls(normalized)

        if not webpage_urls:
            return SchemaComplianceResult(by_url=[])

        all_subjects = {s for s in normalized.subjects() if isinstance(s, URIRef)}

        # Build every subgraph in the main process (no SHACL overhead here).
        tasks: list[tuple[str, str, str]] = []
        for url in webpage_urls:
            subgraph = _build_subgraph(normalized, url, self._depth, all_subjects)
            tasks.append(
                (
                    url,
                    subgraph.serialize(format="nt") if len(subgraph) else "",
                    self._issue_level,
                )
            )

        results: list[UrlComplianceResult] = []
        with ProcessPoolExecutor(
            max_workers=self._max_workers,
            initializer=_init_worker,
            initargs=(
                self._main_shapes_nt,
                self._merchant_shapes_nt,
                self._main_source_map,
                self._merchant_source_map,
            ),
        ) as executor:
            for result in executor.map(_validate_url_worker, tasks):
                results.append(result)

        results.sort(key=lambda r: r.url)
        return SchemaComplianceResult(by_url=results)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_webpage_urls(graph: Graph) -> set[str]:
    urls: set[str] = set()
    for pred in (_SCHEMA_URL_HTTP, _SCHEMA_URL_HTTPS):
        for _, _, o in graph.triples((None, pred, None)):
            if isinstance(o, (URIRef, Literal)):
                urls.add(str(o))
    return urls


def _build_subgraph(
    graph: Graph,
    webpage_url: str,
    depth: int,
    all_subjects: set[URIRef],
) -> Graph:
    # 1. Root IRIs: subjects with schema:url = webpage_url
    root_iris: set[URIRef] = set()
    for pred in (_SCHEMA_URL_HTTP, _SCHEMA_URL_HTTPS):
        for s, _, o in graph.triples((None, pred, None)):
            if isinstance(s, URIRef) and str(o) == webpage_url:
                root_iris.add(s)

    # 2. IRI-prefix children (e.g. /entity/child of /entity)
    child_iris: set[URIRef] = set()
    for root_iri in root_iris:
        prefix = str(root_iri).rstrip("/") + "/"
        for s in all_subjects:
            if str(s).startswith(prefix):
                child_iris.add(s)

    # 3. Expand by depth hops over relationship edges
    entity_iris: set[URIRef] = root_iris | child_iris
    visited: set[URIRef] = set(entity_iris)
    frontier: set[URIRef] = set(entity_iris)
    for _ in range(depth):
        next_frontier: set[URIRef] = set()
        for iri in frontier:
            for _, _, o in graph.triples((iri, None, None)):
                if isinstance(o, URIRef) and o in all_subjects and o not in visited:
                    next_frontier.add(o)
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break

    # 4. Build subgraph — no blank nodes
    subgraph = Graph()
    for iri in visited:
        for s, p, o in graph.triples((iri, None, None)):
            if not isinstance(s, BNode) and not isinstance(o, BNode):
                subgraph.add((s, p, o))
    return subgraph


def _run_with_validator(
    validator,
    data_graph: Graph,
    source_map: dict[str, str],
    issue_level: str = "warning",
) -> tuple[list[IssueEntry], list[IssueEntry]]:
    """Run a pre-warmed Validator on *data_graph*, reusing the shapes cache."""
    if validator is None or len(data_graph) == 0:
        return [], []

    # Reset per-run mutable state; shapes cache on validator.shacl_graph is kept.
    validator.data_graph = data_graph
    validator.pre_inferenced = False
    validator._target_graph = None  # force rebuild from data_graph

    _, report_graph, _ = validator.run()
    return _extract_issues(report_graph, source_map, issue_level)


def _extract_issues(
    report_graph: Graph,
    source_map: dict[str, str],
    issue_level: str = "warning",
) -> tuple[list[IssueEntry], list[IssueEntry]]:
    errors: list[IssueEntry] = []
    warnings: list[IssueEntry] = []

    for node in report_graph.subjects(SH.resultSeverity, None):
        severity_iri = report_graph.value(node, SH.resultSeverity)
        source_shape = report_graph.value(node, SH.sourceShape)
        message = report_graph.value(node, SH.resultMessage)
        focus_node = report_graph.value(node, SH.focusNode)
        result_path = report_graph.value(node, SH.resultPath)
        constraint = report_graph.value(node, SH.sourceConstraintComponent)
        value = report_graph.value(node, SH.value)

        severity_label = (
            str(severity_iri).split("#")[-1] if severity_iri else "Violation"
        )

        entry = IssueEntry(
            severity=severity_label,
            message=str(message) if message is not None else "",
            focus_node=str(focus_node) if focus_node is not None else None,
            path=str(result_path) if result_path is not None else None,
            source_shape=str(source_shape) if source_shape is not None else None,
            shape_source=(
                source_map.get(str(source_shape)) if source_shape is not None else None
            ),
            constraint_component=str(constraint) if constraint is not None else None,
            value=str(value) if value is not None else None,
        )

        if severity_iri == SH.Violation:
            errors.append(entry)
        else:
            warnings.append(entry)

    if issue_level == "error":
        warnings = []

    return errors, warnings


__all__ = [
    "IssueEntry",
    "MerchantResult",
    "SchemaComplianceKpi",
    "SchemaComplianceResult",
    "UrlComplianceResult",
]

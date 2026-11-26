from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rdflib import BNode, Graph
from rdflib.namespace import SH
from rdflib.term import Identifier, URIRef

from wordlift_sdk.validation.shacl import PreparedShaclValidator, format_shacl_path

logger = logging.getLogger(__name__)

DEFAULT_VALIDATION_TIMEOUT_SECONDS = 120.0
# Error details kept per validated graph. The counts stay exact; only the
# per-error rows sent back from the worker are capped, so one pathological page
# cannot flood the pickled result or the run's report.
MAX_ERROR_DETAILS_PER_GRAPH = 100
# How many sh:property hops to climb from an anonymous property shape to the
# named shape that holds it.
_MAX_RULE_PARENT_HOPS = 4


class ValidationMode(str, Enum):
    OFF = "off"
    WARN = "warn"
    FAIL = "fail"


# Module-level worker state — one copy per subprocess, initialised by _init_worker.
# Must be module-level for picklability by ProcessPoolExecutor.
_worker_validator: PreparedShaclValidator | None = None


def _init_worker(shape_specs: list[str] | None) -> None:
    global _worker_validator
    _worker_validator = PreparedShaclValidator.from_shape_specs(shape_specs)


def _rule_id(shape: Identifier | None, shapes_graph: Graph) -> str | None:
    """Return a stable, readable id for the shape that produced a result.

    Named shapes (the bundled Google rules) are their own id. An anonymous
    property shape (``sh:property [ ... ]``) has no stable label, so climb to
    the named shape that holds it; the result path tells the properties apart.
    """
    current = shape
    for _ in range(_MAX_RULE_PARENT_HOPS):
        if current is None:
            return None
        if isinstance(current, URIRef):
            return str(current)
        if not isinstance(current, BNode):
            return None
        current = next(shapes_graph.subjects(SH.property, current), None)
    return None


def _error_detail(report: Graph, node: Identifier, shapes_graph: Graph) -> dict:
    def text(predicate: URIRef) -> str | None:
        value = report.value(node, predicate)
        return str(value) if value is not None else None

    return {
        "rule_id": _rule_id(report.value(node, SH.sourceShape), shapes_graph),
        "path": format_shacl_path(report.value(node, SH.resultPath), shapes_graph),
        "focus_node": text(SH.focusNode),
        "value": text(SH.value),
        "message": text(SH.resultMessage) or "",
    }


def _validate_in_worker(ntriples: str, submit_time: float) -> dict:
    queue_wait_ms = int((time.time() - submit_time) * 1000)
    t_start = time.perf_counter()

    data_graph = Graph()
    data_graph.parse(data=ntriples, format="nt")

    result = _worker_validator.validate_graph(data_graph)
    prepared = _worker_validator.prepared_shapes
    source_map = prepared.shape_source_map
    report = result.report_graph

    warning_sources: dict[str, int] = {}
    error_sources: dict[str, int] = {}
    errors: list[dict] = []
    for node in report.subjects(SH.resultSeverity, SH.Warning):
        shape = next(report.objects(node, SH.sourceShape), None)
        label = source_map.get(shape, "unknown")
        warning_sources[str(label)] = warning_sources.get(str(label), 0) + 1
    for node in report.subjects(SH.resultSeverity, SH.Violation):
        shape = next(report.objects(node, SH.sourceShape), None)
        label = str(source_map.get(shape, "unknown"))
        error_sources[label] = error_sources.get(label, 0) + 1
        errors.append(
            {"rule_set": label, **_error_detail(report, node, prepared.shapes_graph)}
        )
    # Report graph iteration order is arbitrary; sort so the cap keeps the same
    # rows from run to run.
    errors.sort(
        key=lambda e: tuple(
            e[k] or "" for k in ("rule_set", "rule_id", "path", "focus_node", "value")
        )
    )

    return {
        "passed": bool(result.conforms),
        "warning_sources": dict(sorted(warning_sources.items())),
        "error_sources": dict(sorted(error_sources.items())),
        "errors": errors[:MAX_ERROR_DETAILS_PER_GRAPH],
        "queue_wait_ms": queue_wait_ms,
        "validation_ms": int((time.perf_counter() - t_start) * 1000),
    }


@dataclass(frozen=True)
class ValidationErrorDetail:
    """One SHACL violation (severity error) in a validated graph."""

    rule_set: str
    rule_id: str | None
    path: str | None
    focus_node: str | None
    value: str | None
    message: str


@dataclass
class ValidationOutcome:
    passed: bool
    warning_sources: dict[str, int]
    error_sources: dict[str, int]
    queue_wait_ms: int
    validation_ms: int
    # At most MAX_ERROR_DETAILS_PER_GRAPH entries; error_count stays exact.
    errors: list[ValidationErrorDetail] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def warning_count(self) -> int:
        return sum(self.warning_sources.values())

    @property
    def error_count(self) -> int:
        return sum(self.error_sources.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass": self.passed,
            "fail": self.failed,
            "warnings": {"count": self.warning_count, "sources": self.warning_sources},
            "errors": {"count": self.error_count, "sources": self.error_sources},
        }


class ShaclValidationService:
    def __init__(
        self,
        shape_specs: list[str] | None,
        mode: ValidationMode,
        pool_size: int = 1,
        timeout_seconds: float = DEFAULT_VALIDATION_TIMEOUT_SECONDS,
    ) -> None:
        self._mode = mode
        self._timeout_seconds = timeout_seconds
        self._executor: ProcessPoolExecutor | None = None
        if mode != ValidationMode.OFF:
            self._executor = ProcessPoolExecutor(
                max_workers=pool_size,
                initializer=_init_worker,
                initargs=(shape_specs,),
            )
            logger.info(
                "Created SHACL process pool with %d workers (mode=%s)",
                pool_size,
                mode,
            )

    @property
    def mode(self) -> ValidationMode:
        return self._mode

    async def validate(self, graph: Graph) -> ValidationOutcome | None:
        """Validate *graph* against the configured SHACL shapes.

        Returns ``None`` when validation is disabled (mode=off) or skipped due
        to a timeout or broken executor.
        """
        if self._mode == ValidationMode.OFF or self._executor is None:
            return None
        ntriples = graph.serialize(format="nt")
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    functools.partial(_validate_in_worker, ntriples, time.time()),
                ),
                timeout=self._timeout_seconds,
            )
        except (asyncio.TimeoutError, concurrent.futures.BrokenExecutor) as exc:
            logger.warning("SHACL validation skipped: %s (%s)", type(exc).__name__, exc)
            return None
        return ValidationOutcome(
            passed=result["passed"],
            warning_sources=result["warning_sources"],
            error_sources=result["error_sources"],
            queue_wait_ms=result["queue_wait_ms"],
            validation_ms=result["validation_ms"],
            errors=[ValidationErrorDetail(**e) for e in result.get("errors", [])],
        )

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

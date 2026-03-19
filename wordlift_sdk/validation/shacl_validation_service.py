from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pyshacl import validate as pyshacl_validate
from rdflib import Graph
from rdflib.namespace import SH

from wordlift_sdk.validation.shacl import load_shapes_graph, normalize_schema_org_uris

logger = logging.getLogger(__name__)

DEFAULT_VALIDATION_TIMEOUT_SECONDS = 120.0


class ValidationMode(str, Enum):
    OFF = "off"
    WARN = "warn"
    FAIL = "fail"


# Module-level worker state — one copy per subprocess, initialised by _init_worker.
# Must be module-level for picklability by ProcessPoolExecutor.
_worker_shapes_graph: Graph | None = None
_worker_source_map: dict = {}


def _init_worker(shape_specs: list[str] | None) -> None:
    global _worker_shapes_graph, _worker_source_map
    _worker_shapes_graph, _worker_source_map = load_shapes_graph(shape_specs)


def _validate_in_worker(ntriples: str, submit_time: float) -> dict:
    queue_wait_ms = int((time.time() - submit_time) * 1000)
    t_start = time.perf_counter()

    data_graph = Graph()
    data_graph.parse(data=ntriples, format="nt")
    data_graph = normalize_schema_org_uris(data_graph)

    conforms, report_graph, _ = pyshacl_validate(
        data_graph,
        shacl_graph=_worker_shapes_graph,
        inference="rdfs",
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )

    warning_sources: dict[str, int] = {}
    error_sources: dict[str, int] = {}
    for node in report_graph.subjects(SH.resultSeverity, SH.Warning):
        shape = next(report_graph.objects(node, SH.sourceShape), None)
        label = _worker_source_map.get(shape, "unknown")
        warning_sources[str(label)] = warning_sources.get(str(label), 0) + 1
    for node in report_graph.subjects(SH.resultSeverity, SH.Violation):
        shape = next(report_graph.objects(node, SH.sourceShape), None)
        label = _worker_source_map.get(shape, "unknown")
        error_sources[str(label)] = error_sources.get(str(label), 0) + 1

    return {
        "passed": bool(conforms),
        "warning_sources": dict(sorted(warning_sources.items())),
        "error_sources": dict(sorted(error_sources.items())),
        "queue_wait_ms": queue_wait_ms,
        "validation_ms": int((time.perf_counter() - t_start) * 1000),
    }


@dataclass
class ValidationOutcome:
    passed: bool
    warning_sources: dict[str, int]
    error_sources: dict[str, int]
    queue_wait_ms: int
    validation_ms: int

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
        )

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

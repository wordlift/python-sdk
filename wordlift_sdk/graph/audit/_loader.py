"""Load an rdflib Graph from a file, collecting parse errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph

_FORMAT_MAP: dict[str, str] = {
    ".ttl": "turtle",
    ".turtle": "turtle",
    ".jsonld": "json-ld",
    ".json-ld": "json-ld",
    ".json": "json-ld",
    ".nt": "nt",
    ".n3": "n3",
    ".rdf": "xml",
    ".xml": "xml",
    ".owl": "xml",
}


@dataclass
class LoadError:
    code: str
    severity: str
    message: str
    position: int | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.position is not None:
            d["position"] = self.position
        return d


@dataclass
class LoadResult:
    graph: Graph
    errors: list[LoadError] = field(default_factory=list)


def load_graph(path: str | Path) -> LoadResult:
    """
    Parse *path* into an rdflib Graph.

    Format is auto-detected from the file extension.  Parse errors are
    captured as :class:`LoadError` entries rather than raised as exceptions
    so that the audit can still report partial results.
    """
    p = Path(path)
    fmt = _FORMAT_MAP.get(p.suffix.lower())
    graph = Graph()
    errors: list[LoadError] = []

    try:
        if fmt:
            graph.parse(str(p), format=fmt)
        else:
            graph.parse(str(p))  # let rdflib sniff the format
    except Exception as exc:  # noqa: BLE001
        errors.append(
            LoadError(
                code="parse_error",
                severity="Violation",
                message=str(exc),
            )
        )

    return LoadResult(graph=graph, errors=errors)


__all__ = ["LoadError", "LoadResult", "load_graph"]

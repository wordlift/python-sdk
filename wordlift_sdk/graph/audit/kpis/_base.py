"""Base protocol for KPI collectors."""

from __future__ import annotations

from typing import Any, Protocol

from rdflib import Graph


class KpiCollector(Protocol):
    """Single-responsibility KPI collector over an rdflib Graph."""

    def collect(self, graph: Graph) -> Any: ...


__all__ = ["KpiCollector"]

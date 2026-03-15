"""Graph utilities."""

from __future__ import annotations

from .._lazy_exports import resolve_attr

__all__ = ["AuditOptions", "GraphAuditReport", "GraphAuditor"]


_EXPORTS = {
    "AuditOptions": ("wordlift_sdk.graph.audit", "AuditOptions"),
    "GraphAuditReport": ("wordlift_sdk.graph.audit", "GraphAuditReport"),
    "GraphAuditor": ("wordlift_sdk.graph.audit", "GraphAuditor"),
}


def __getattr__(name: str):
    return resolve_attr(
        name=name,
        module_name="wordlift_sdk.graph",
        exports=_EXPORTS,
        extra="graph",
    )

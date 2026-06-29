"""Graph audit module: KPI extraction from RDF graph files."""

from __future__ import annotations

from ._auditor import AuditOptions, GraphAuditor
from ._entity_matrix import build_entity_matrix
from ._kpi_snapshot import (
    GraphKpiSnapshotOptions,
    build_graph_kpi_api_payload,
    calculate_graph_kpi_snapshot,
)
from ._loader import LoadError, LoadResult, load_graph
from ._profile import shape_specs_for_profile
from ._report import GraphAuditReport
from .kpis import (
    BrokenLinksKpi,
    BrokenLinksResult,
    DuplicatesKpi,
    DuplicatesResult,
    EdgeNodeRatioKpi,
    EdgeNodeRatioResult,
    EdgesKpi,
    EdgesResult,
    EntityTypesKpi,
    EntityTypesResult,
    IsolatedGraphsKpi,
    IsolatedGraphsResult,
    IssueEntry,
    MerchantResult,
    OrphansKpi,
    OrphansResult,
    PropertiesKpi,
    PropertiesResult,
    RichSnippetsKpi,
    RichSnippetsResult,
    SchemaComplianceKpi,
    SchemaComplianceResult,
    TotalsKpi,
    TotalsResult,
    UniqueUrlsKpi,
    UniqueUrlsResult,
    UrlComplianceResult,
)
from .kpis.schema_compliance import build_subgraph

__all__ = [
    "AuditOptions",
    "BrokenLinksKpi",
    "BrokenLinksResult",
    "DuplicatesKpi",
    "DuplicatesResult",
    "EdgeNodeRatioKpi",
    "EdgeNodeRatioResult",
    "EdgesKpi",
    "EdgesResult",
    "EntityTypesKpi",
    "EntityTypesResult",
    "GraphAuditReport",
    "GraphAuditor",
    "GraphKpiSnapshotOptions",
    "IsolatedGraphsKpi",
    "IsolatedGraphsResult",
    "IssueEntry",
    "LoadError",
    "LoadResult",
    "MerchantResult",
    "OrphansKpi",
    "OrphansResult",
    "PropertiesKpi",
    "PropertiesResult",
    "RichSnippetsKpi",
    "RichSnippetsResult",
    "SchemaComplianceKpi",
    "SchemaComplianceResult",
    "TotalsKpi",
    "TotalsResult",
    "UniqueUrlsKpi",
    "UniqueUrlsResult",
    "UrlComplianceResult",
    "build_entity_matrix",
    "build_graph_kpi_api_payload",
    "build_subgraph",
    "calculate_graph_kpi_snapshot",
    "load_graph",
    "shape_specs_for_profile",
]

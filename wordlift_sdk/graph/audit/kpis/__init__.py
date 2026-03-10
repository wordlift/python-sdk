"""KPI collectors for graph audit."""

from __future__ import annotations

from .broken_links import BrokenLinksKpi, BrokenLinksResult
from .duplicates import DuplicatesKpi, DuplicatesResult
from .edge_node_ratio import EdgeNodeRatioKpi, EdgeNodeRatioResult
from .edges import EdgesKpi, EdgesResult
from .entity_types import EntityTypesKpi, EntityTypesResult
from .isolated_graphs import IsolatedGraphsKpi, IsolatedGraphsResult
from .orphans import OrphansKpi, OrphansResult
from .properties import PropertiesKpi, PropertiesResult
from .rich_snippets import RichSnippetsKpi, RichSnippetsResult
from .schema_compliance import (
    IssueEntry,
    MerchantResult,
    SchemaComplianceKpi,
    SchemaComplianceResult,
    UrlComplianceResult,
)
from .totals import TotalsKpi, TotalsResult
from .unique_urls import UniqueUrlsKpi, UniqueUrlsResult

__all__ = [
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
    "IsolatedGraphsKpi",
    "IsolatedGraphsResult",
    "IssueEntry",
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
]

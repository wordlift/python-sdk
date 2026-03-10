"""GraphAuditor: orchestrates all KPI collectors concurrently."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from wordlift_sdk.graph.audit._loader import load_graph
from wordlift_sdk.graph.audit._profile import shape_specs_for_profile
from wordlift_sdk.graph.audit._report import GraphAuditReport
from wordlift_sdk.graph.audit.kpis import (
    BrokenLinksKpi,
    DuplicatesKpi,
    EdgeNodeRatioKpi,
    EdgesKpi,
    EntityTypesKpi,
    IsolatedGraphsKpi,
    OrphansKpi,
    PropertiesKpi,
    RichSnippetsKpi,
    SchemaComplianceKpi,
    TotalsKpi,
    UniqueUrlsKpi,
)
from wordlift_sdk.kg_build.config import ProfileDefinition


@dataclass
class AuditOptions:
    """Configuration for a :class:`GraphAuditor` run."""

    profile: ProfileDefinition | None = None
    subgraph_depth: int = 1
    list_isolated_components: bool = False
    rich_snippets_granularity: Literal["counts", "entities"] = "counts"
    max_workers: int | None = None


class GraphAuditor:
    """
    Audit a graph file and return a :class:`~wordlift_sdk.graph.audit.GraphAuditReport`.

    All KPI collectors run concurrently via a :class:`~concurrent.futures.ThreadPoolExecutor`.
    :class:`~wordlift_sdk.graph.audit.kpis.SchemaComplianceKpi` further
    parallelises SHACL runs per webpage URL within the same pool.

    Usage::

        from wordlift_sdk.graph.audit import GraphAuditor, AuditOptions

        report = GraphAuditor().audit("output/graph.ttl")
        print(report.to_text())
        print(report.to_dict())
    """

    def audit(
        self,
        path: str | Path,
        options: AuditOptions | None = None,
    ) -> GraphAuditReport:
        opts = options or AuditOptions()
        shape_specs = shape_specs_for_profile(opts.profile)

        load_result = load_graph(path)
        graph = load_result.graph

        # Fast, GIL-friendly collectors run concurrently in a thread pool.
        thread_collectors = {
            "entity_types": EntityTypesKpi(),
            "properties": PropertiesKpi(),
            "totals": TotalsKpi(),
            "unique_urls": UniqueUrlsKpi(),
            "edges": EdgesKpi(),
            "rich_snippets": RichSnippetsKpi(
                granularity=opts.rich_snippets_granularity,
            ),
            "orphans": OrphansKpi(),
            "broken_links": BrokenLinksKpi(),
            "isolated_graphs": IsolatedGraphsKpi(
                list_components=opts.list_isolated_components,
            ),
            "edge_node_ratio": EdgeNodeRatioKpi(),
            "duplicates": DuplicatesKpi(),
        }

        results: dict = {}
        with ThreadPoolExecutor(max_workers=opts.max_workers) as executor:
            futures = {
                executor.submit(collector.collect, graph): name
                for name, collector in thread_collectors.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                results[name] = future.result()

        # SchemaComplianceKpi uses ProcessPoolExecutor internally — run outside
        # the thread pool to avoid nesting executor contexts.
        schema_kpi = SchemaComplianceKpi(
            shape_specs=shape_specs,
            depth=opts.subgraph_depth,
            max_workers=opts.max_workers,
        )
        results["schema_compliance"] = schema_kpi.collect(graph)

        return GraphAuditReport(
            load_errors=load_result.errors,
            entity_types=results["entity_types"],
            properties=results["properties"],
            totals=results["totals"],
            unique_urls=results["unique_urls"],
            edges=results["edges"],
            rich_snippets=results["rich_snippets"],
            orphans=results["orphans"],
            broken_links=results["broken_links"],
            isolated_graphs=results["isolated_graphs"],
            edge_node_ratio=results["edge_node_ratio"],
            schema_compliance=results["schema_compliance"],
            duplicates=results["duplicates"],
        )


__all__ = ["AuditOptions", "GraphAuditor"]

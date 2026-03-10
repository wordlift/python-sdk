"""GraphAuditReport: aggregated result of all KPI collectors."""

from __future__ import annotations

from dataclasses import dataclass

from wordlift_sdk.graph.audit._loader import LoadError
from wordlift_sdk.graph.audit.kpis import (
    BrokenLinksResult,
    DuplicatesResult,
    EdgeNodeRatioResult,
    EdgesResult,
    EntityTypesResult,
    IsolatedGraphsResult,
    OrphansResult,
    PropertiesResult,
    RichSnippetsResult,
    SchemaComplianceResult,
    TotalsResult,
    UniqueUrlsResult,
)


@dataclass
class GraphAuditReport:
    load_errors: list[LoadError]
    entity_types: EntityTypesResult
    properties: PropertiesResult
    totals: TotalsResult
    unique_urls: UniqueUrlsResult
    edges: EdgesResult
    rich_snippets: RichSnippetsResult
    orphans: OrphansResult
    broken_links: BrokenLinksResult
    isolated_graphs: IsolatedGraphsResult
    edge_node_ratio: EdgeNodeRatioResult
    schema_compliance: SchemaComplianceResult
    duplicates: DuplicatesResult

    def to_dict(self) -> dict:
        result: dict = {}
        if self.load_errors:
            result["load_errors"] = [e.to_dict() for e in self.load_errors]
        result.update(self.entity_types.to_dict())
        result.update(self.properties.to_dict())
        result.update(self.totals.to_dict())
        result.update(self.unique_urls.to_dict())
        result.update(self.edges.to_dict())
        result.update(self.rich_snippets.to_dict())
        result.update(self.orphans.to_dict())
        result.update(self.broken_links.to_dict())
        result.update(self.isolated_graphs.to_dict())
        result.update(self.edge_node_ratio.to_dict())
        result.update(self.schema_compliance.to_dict())
        result.update(self.duplicates.to_dict())
        return result

    def to_text(self) -> str:
        lines: list[str] = ["=== Graph Audit Report ===", ""]

        # Load errors
        if self.load_errors:
            lines.append("--- Load Errors ---")
            for e in self.load_errors:
                lines.append(f"  [{e.severity}] {e.code}: {e.message}")
            lines.append("")

        # Totals
        t = self.totals
        lines += [
            "--- Totals ---",
            f"  Entities      : {t.total_entities}",
            f"  Properties    : {t.total_properties}",
            f"  Triples       : {t.total_triples}",
            f"  Unique URLs   : {self.unique_urls.count}",
            f"  Edges         : {self.edges.count}",
            f"  Edge/Node ratio: {self.edge_node_ratio.ratio}",
            "",
        ]

        # Entity types
        lines.append("--- Entity Types ---")
        for type_iri, count in self.entity_types.by_type.items():
            lines.append(f"  {type_iri}: {count}")
        lines.append("")

        # Properties
        lines.append("--- Properties ---")
        for pred, count in self.properties.by_predicate.items():
            lines.append(f"  {pred}: {count}")
        lines.append("")

        # Connectivity / topology
        lines += [
            "--- Connectivity ---",
            f"  Orphans          : {self.orphans.count}",
            f"  Broken links     : {self.broken_links.count}",
            f"  Graph components : {self.isolated_graphs.component_count}",
            f"  Duplicate groups : {self.duplicates.count}",
            "",
        ]

        # Rich snippets
        lines.append("--- Rich Snippets ---")
        lines.append("  Eligible valid:")
        for t, v in self.rich_snippets.eligible_valid.items():
            lines.append(f"    {t}: {v}")
        lines.append("  Eligible invalid:")
        for t, v in self.rich_snippets.eligible_invalid.items():
            lines.append(f"    {t}: {v}")
        lines.append("")

        # Schema compliance
        lines.append("--- Schema Compliance ---")
        for r in self.schema_compliance.by_url:
            conforms = r.error_count == 0
            status = "OK" if conforms else "FAIL"
            lines.append(
                f"  [{status}] {r.url}  (errors={r.error_count}, warnings={r.warning_count})"
            )
            merchant = r.google_merchant
            m_status = "eligible" if merchant.eligible else "not eligible"
            lines.append(f"         merchant: {m_status}")
            for e in r.errors:
                lines.append(f"         ERROR: {e.message} (focus={e.focus_node})")
            for w in r.warnings:
                lines.append(f"         WARN : {w.message} (focus={w.focus_node})")
        lines.append("")

        return "\n".join(lines)


__all__ = ["GraphAuditReport"]

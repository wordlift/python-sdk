"""Fast graph KPI snapshots for WordLift API uploads."""

from __future__ import annotations

import re
from bisect import bisect_left
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from rdflib import BNode, Graph, RDF, URIRef
from rdflib import Literal as RDFLiteral
from rdflib.namespace import SH
from rdflib.plugins.parsers.ntriples import W3CNTriplesParser

from ._loader import LoadError, load_graph
from ._profile import shape_specs_for_profile
from wordlift_sdk.validation.shacl import resolve_shape_specs
from wordlift_sdk.validation.shacl import (
    PreparedShaclValidator,
    _normalize_schema_org_uris,  # type: ignore[attr-defined]
    _should_skip_schemaorg_subclass_range_warning,  # type: ignore[attr-defined]
)
from wordlift_sdk.kg_build.config import ProfileDefinition

SCHEMA = "http://schema.org/"
SCHEMA_HTTPS = "https://schema.org/"
SCHEMA_URL_HTTP = URIRef(SCHEMA + "url")
SCHEMA_URL_HTTPS = URIRef(SCHEMA_HTTPS + "url")

RICH_RESULT_TYPES = {
    "Article",
    "BlogPosting",
    "NewsArticle",
    "Product",
    "ProductGroup",
    "FAQPage",
    "HowTo",
    "Event",
    "Review",
    "SoftwareApplication",
    "VideoObject",
    "Organization",
    "LocalBusiness",
    "Recipe",
    "Course",
    "JobPosting",
    "QAPage",
}
MERCHANT_SHAPE = "google-merchant-listing.ttl"


@dataclass(frozen=True)
class GraphKpiSnapshotOptions:
    website_host: str | None = None
    graph_hosts: set[str] | None = None
    profile: ProfileDefinition | None = None
    builtin_shapes: list[str] | None = None
    exclude_builtin_shapes: list[str] | None = None
    extra_shapes: list[str] | None = None
    include_default_shapes: bool = True
    subgraph_depth: int = 1
    issue_level: str = "warning"
    shacl_workers: int | None = None
    memory_mode: Literal["full", "streaming"] = "full"


def calculate_graph_kpi_snapshot(
    path: str | Path,
    options: GraphKpiSnapshotOptions | None = None,
) -> dict[str, Any]:
    opts = options or GraphKpiSnapshotOptions()
    if opts.memory_mode == "streaming":
        return _calculate_streaming_graph_kpi_snapshot(Path(path), opts)

    load_result = load_graph(path)
    graph = load_result.graph
    detail = _build_fast_kpis(Path(path), graph, opts.website_host, opts.graph_hosts)
    detail["load_errors"] = [error.to_dict() for error in load_result.errors]
    detail["schema_compliance"] = _build_schema_compliance(graph, opts)
    return detail


def build_graph_kpi_api_payload(
    snapshot: dict[str, Any],
    *,
    snapshot_date: date | str,
    calculated_at: datetime | str | None = None,
    snapshot_origin: str = "worai_graph_kpis",
) -> dict[str, Any]:
    if isinstance(snapshot_date, date):
        snapshot_date_value = snapshot_date.isoformat()
    else:
        snapshot_date_value = snapshot_date

    if calculated_at is None:
        calculated_at_value = (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
    elif isinstance(calculated_at, datetime):
        calculated_at_value = (
            calculated_at.astimezone(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    else:
        calculated_at_value = calculated_at

    totals = snapshot.get("totals") or {}
    edges = snapshot.get("edges") or {}
    connectivity = snapshot.get("connectivity") or {}
    integrity = snapshot.get("integrity") or {}
    topology = snapshot.get("topology") or {}
    compliance = snapshot.get("schema_compliance") or {}

    all_total_entities = totals.get("total_entity_count", 0)
    all_total_typed_entities = totals.get("total_typed_entity_count", 0)
    all_total_properties = totals.get("total_property_count", 0)
    all_total_triples = totals.get("total_triples", 0)
    all_unique_properties_count = totals.get("unique_property_count", 0)
    all_rdf_type_triples_count = totals.get("rdf_type_triples", 0)
    all_internal_edges_count = edges.get("total_internal_edges", 0)
    all_unique_urls_count = totals.get("unique_urls_within_website_scope", 0)
    all_broken_links_count = integrity.get("broken_internal_edge_count", 0)
    all_duplicates_count = integrity.get("duplicate_url_group_count", 0)
    all_duplicate_extra_entities_count = integrity.get(
        "duplicate_extra_entity_count", 0
    )
    schema_compliance_errors = compliance.get("errors", 0)
    schema_compliance_warnings = compliance.get("warnings", 0)
    schema_compliance_urls_checked = compliance.get("urls_checked", 0)
    rich_snippets_valid_count = compliance.get("google_merchant_eligible", 0)
    rich_snippets_invalid_count = compliance.get("google_merchant_not_eligible", 0)
    rich_snippet_candidate_entities = (
        snapshot.get("rich_snippet_candidate_entities") or {}
    )

    payload: dict[str, Any] = {
        "snapshot_date": snapshot_date_value,
        "calculated_at": calculated_at_value,
        "snapshot_origin": snapshot_origin,
        "all_total_entities": all_total_entities,
        "all_total_typed_entities": all_total_typed_entities,
        "all_total_properties": all_total_properties,
        "all_total_triples": all_total_triples,
        "all_unique_properties_count": all_unique_properties_count,
        "all_rdf_type_triples_count": all_rdf_type_triples_count,
        "all_internal_nodes_count": connectivity.get("internal_node_count", 0),
        "all_internal_edges_count": all_internal_edges_count,
        "all_external_edges_count": 0,
        "all_edges_count": all_internal_edges_count,
        "all_edge_predicate_counts": edges.get("edge_predicate_counts") or {},
        "all_edge_node_ratio": edges.get("edge_to_node_ratio", 0),
        "all_unique_urls_count": all_unique_urls_count,
        "all_orphans_count": connectivity.get("orphan_entity_count", 0),
        "all_broken_links_count": all_broken_links_count,
        "all_isolated_graphs_count": topology.get("isolated_graph_count", 0),
        "all_largest_component_nodes_count": topology.get(
            "largest_component_node_count", 0
        ),
        "all_duplicates_count": all_duplicates_count,
        "all_duplicate_extra_entities_count": all_duplicate_extra_entities_count,
        "rich_snippets_candidate_count": rich_snippet_candidate_entities.get(
            "total", 0
        ),
        "rich_snippets_valid_count": rich_snippets_valid_count,
        "rich_snippets_invalid_count": rich_snippets_invalid_count,
        "rich_snippets_by_type": rich_snippet_candidate_entities.get("by_type", {}),
        "schema_compliance_errors": schema_compliance_errors,
        "schema_compliance_warnings": schema_compliance_warnings,
        "schema_compliance_urls_checked": schema_compliance_urls_checked,
        "schema_compliance_urls_with_errors": compliance.get("urls_with_errors", 0),
        "schema_compliance_urls_with_warnings": compliance.get("urls_with_warnings", 0),
        "all_entity_types": snapshot.get("entity_type_counts") or {},
        "all_properties_by_predicate": snapshot.get("property_counts") or {},
    }
    payload["graph_health_score"] = _calculate_graph_health_score(payload)
    payload["density_score"] = payload["all_edge_node_ratio"]
    if compliance.get("skipped"):
        payload["schema_compliance_skipped"] = 1
        payload["graph_health_score_partial"] = 1
    else:
        payload["schema_compliance_skipped"] = 0
        payload["graph_health_score_partial"] = 0
    return _numeric_only(payload)


def _calculate_graph_health_score(metrics: dict[str, Any]) -> int:
    score_value = (
        100
        - _safe_rate(
            metrics.get("schema_compliance_errors"),
            metrics.get("schema_compliance_urls_checked"),
        )
        * 35
        - _safe_rate(
            metrics.get("schema_compliance_warnings"),
            metrics.get("schema_compliance_urls_checked"),
        )
        * 10
        - _safe_rate(
            metrics.get("all_broken_links_count"),
            metrics.get("all_internal_edges_count"),
        )
        * 25
        - _safe_rate(
            metrics.get("all_duplicates_count"),
            metrics.get("all_unique_urls_count"),
        )
        * 20
        + _rich_snippet_valid_rate(metrics) * 5
    )
    score = int(score_value + 0.5)
    if _to_float(metrics.get("schema_compliance_skipped")) > 0:
        score -= 20
    return max(0, min(100, score))


def _rich_snippet_valid_rate(metrics: dict[str, Any]) -> float:
    valid = _to_float(metrics.get("rich_snippets_valid_count"))
    invalid = _to_float(metrics.get("rich_snippets_invalid_count"))
    total = valid + invalid
    if total <= 0:
        return 0
    return valid / total


def _safe_rate(numerator: Any, denominator: Any) -> float:
    denominator_value = _to_float(denominator)
    if denominator_value <= 0:
        return 0
    return _to_float(numerator) / denominator_value


def _to_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    return 0


def schema_term(uri: Any) -> str | None:
    value = str(uri)
    if value.startswith(SCHEMA):
        return value.removeprefix(SCHEMA)
    if value.startswith(SCHEMA_HTTPS):
        return value.removeprefix(SCHEMA_HTTPS)
    return None


def compact_uri(uri: Any) -> str:
    term = schema_term(uri)
    if term:
        return f"schema:{term}"
    if str(uri) == str(RDF.type):
        return "rdf:type"
    return str(uri)


def host_of_uri(value: Any) -> str | None:
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed.netloc.lower()


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, netloc, path, "", ""))


def infer_website_host(urls: set[str]) -> str | None:
    hosts = Counter(host for url in urls if (host := host_of_uri(url)))
    return hosts.most_common(1)[0][0] if hosts else None


def infer_graph_hosts(subjects: set[URIRef]) -> set[str]:
    hosts = Counter(host for subject in subjects if (host := host_of_uri(subject)))
    if not hosts:
        return set()
    top_count = hosts.most_common(1)[0][1]
    return {host for host, count in hosts.items() if count >= max(3, top_count * 0.05)}


def is_website_url(value: str, website_host: str | None) -> bool:
    return bool(website_host) and host_of_uri(value) == website_host


def is_ignored_duplicate_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.path.startswith("/api/v1.0/")
        or parsed.path.startswith("/checkout/")
        or any(part.startswith("utm_") for part in parsed.query.split("&"))
    )


def is_internal_resource(value: URIRef, graph_hosts: set[str]) -> bool:
    host = host_of_uri(value)
    return bool(host and host in graph_hosts)


def is_expected_homepage_identity_overlap(
    url: str,
    subjects_for_url: set[str],
    types_by_subject: dict[Any, set[str]],
) -> bool:
    if urlsplit(url).path not in {"", "/"}:
        return False
    allowed_types = {"Organization", "FinancialService", "WebSite"}
    homepage_types = [
        types_by_subject.get(URIRef(subject), set()).intersection(allowed_types)
        for subject in subjects_for_url
    ]
    return bool(homepage_types) and all(
        subject_types for subject_types in homepage_types
    )


def connected_components(
    nodes: set[URIRef], adjacency: dict[URIRef, set[URIRef]]
) -> list[int]:
    unseen = set(nodes)
    sizes: list[int] = []
    while unseen:
        start = unseen.pop()
        queue: deque[URIRef] = deque([start])
        size = 1
        while queue:
            node = queue.popleft()
            for neighbor in adjacency.get(node, set()):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
                    size += 1
        sizes.append(size)
    return sorted(sizes, reverse=True)


def _schema_urls(graph: Graph) -> set[str]:
    urls: set[str] = set()
    for predicate in (SCHEMA_URL_HTTP, SCHEMA_URL_HTTPS):
        urls.update(
            str(obj)
            for obj in graph.objects(None, predicate)
            if isinstance(obj, (RDFLiteral, URIRef))
        )
    return urls


def _build_fast_kpis(
    path: Path,
    graph: Graph,
    website_host: str | None,
    graph_hosts: set[str] | None,
) -> dict[str, Any]:
    uri_subjects = {
        subject for subject in graph.subjects() if isinstance(subject, URIRef)
    }
    all_schema_urls = _schema_urls(graph)
    inferred_website_host = infer_website_host(all_schema_urls)
    website_host = (website_host or inferred_website_host or "").lower() or None
    graph_hosts = (
        {host.lower() for host in graph_hosts}
        if graph_hosts
        else infer_graph_hosts(uri_subjects)
    )

    entity_type_counts: Counter[str] = Counter()
    typed_subjects: set[Any] = set()
    types_by_subject: defaultdict[Any, set[str]] = defaultdict(set)
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        typed_subjects.add(subject)
        term = schema_term(obj)
        if term:
            entity_type_counts[term] += 1
            types_by_subject[subject].add(term)

    property_counts = Counter(
        compact_uri(predicate) for _, predicate, _ in graph if predicate != RDF.type
    )
    rdf_type_triples = sum(1 for _ in graph.triples((None, RDF.type, None)))
    property_assertions = len(graph) - rdf_type_triples

    website_urls: defaultdict[str, set[str]] = defaultdict(set)
    raw_website_urls: defaultdict[str, set[str]] = defaultdict(set)
    for predicate in (SCHEMA_URL_HTTP, SCHEMA_URL_HTTPS):
        for subject, _, obj in graph.triples((None, predicate, None)):
            url = str(obj)
            if is_website_url(url, website_host):
                website_urls[normalize_url(url)].add(str(subject))
                if not is_ignored_duplicate_url(url):
                    raw_website_urls[url].add(str(subject))

    duplicate_url_groups = {
        url: sorted(subjects_for_url)
        for url, subjects_for_url in raw_website_urls.items()
        if len(subjects_for_url) > 1
        and not is_expected_homepage_identity_overlap(
            url, subjects_for_url, types_by_subject
        )
    }
    duplicate_extra_entities = sum(
        len(subjects_for_url) - 1 for subjects_for_url in duplicate_url_groups.values()
    )

    rich_candidate_subjects = {
        str(subject)
        for subject, subject_types in types_by_subject.items()
        if isinstance(subject, URIRef) and subject_types.intersection(RICH_RESULT_TYPES)
    }
    rich_candidate_by_type = {
        entity_type: entity_type_counts[entity_type]
        for entity_type in sorted(RICH_RESULT_TYPES)
        if entity_type_counts.get(entity_type)
    }

    internal_nodes = {
        node for node in uri_subjects if is_internal_resource(node, graph_hosts)
    }
    internal_edges: list[tuple[URIRef, URIRef, URIRef]] = []
    edge_predicates: Counter[str] = Counter()
    dangling_internal_edges: list[tuple[str, str, str]] = []
    adjacency: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    degree: Counter[URIRef] = Counter()

    for subject, predicate, obj in graph:
        if (
            predicate == RDF.type
            or not isinstance(subject, URIRef)
            or not isinstance(obj, URIRef)
        ):
            continue
        if not is_internal_resource(subject, graph_hosts):
            continue
        internal_edges.append((subject, predicate, obj))
        edge_predicates[compact_uri(predicate)] += 1
        degree[subject] += 1
        if is_internal_resource(obj, graph_hosts):
            degree[obj] += 1
            adjacency[subject].add(obj)
            adjacency[obj].add(subject)
            if obj not in uri_subjects:
                dangling_internal_edges.append(
                    (str(subject), compact_uri(predicate), str(obj))
                )

    orphan_entities = sorted(
        str(node)
        for node in internal_nodes
        if node in typed_subjects and degree[node] == 0
    )
    component_sizes = connected_components(internal_nodes, adjacency)

    return {
        "source_file": str(path),
        "scope": {
            "website_host": website_host,
            "website_host_inferred": inferred_website_host,
            "graph_hosts": sorted(graph_hosts),
        },
        "totals": {
            "total_triples": len(graph),
            "total_entity_count": len(uri_subjects),
            "total_typed_entity_count": len(typed_subjects),
            "total_property_count": property_assertions,
            "unique_property_count": len(set(graph.predicates()) - {RDF.type}),
            "rdf_type_triples": rdf_type_triples,
            "unique_urls_within_website_scope": len(website_urls),
        },
        "entity_type_counts": dict(entity_type_counts.most_common()),
        "property_counts": dict(property_counts.most_common()),
        "rich_snippet_candidate_entities": {
            "total": len(rich_candidate_subjects),
            "by_type": rich_candidate_by_type,
        },
        "edges": {
            "total_internal_edges": len(internal_edges),
            "edge_predicate_counts": dict(edge_predicates.most_common()),
            "edge_to_node_ratio": round(len(internal_edges) / len(internal_nodes), 4)
            if internal_nodes
            else 0,
        },
        "connectivity": {
            "internal_node_count": len(internal_nodes),
            "orphan_entity_count": len(orphan_entities),
            "orphan_entity_examples": orphan_entities[:25],
        },
        "integrity": {
            "broken_internal_edge_count": len(dangling_internal_edges),
            "broken_internal_edge_examples": dangling_internal_edges[:25],
            "duplicate_url_group_count": len(duplicate_url_groups),
            "duplicate_extra_entity_count": duplicate_extra_entities,
            "duplicate_url_examples": dict(list(duplicate_url_groups.items())[:25]),
        },
        "topology": {
            "isolated_graph_count": len(component_sizes),
            "largest_component_node_count": component_sizes[0]
            if component_sizes
            else 0,
            "component_size_top_10": component_sizes[:10],
        },
    }


def _calculate_streaming_graph_kpi_snapshot(
    path: Path,
    opts: GraphKpiSnapshotOptions,
) -> dict[str, Any]:
    if path.suffix.lower() != ".nt":
        raise ValueError("Streaming graph KPI mode requires an N-Triples (.nt) file.")

    load_errors: list[LoadError] = []
    try:
        detail = _build_streaming_fast_kpis(path, opts.website_host, opts.graph_hosts)
    except Exception as exc:  # noqa: BLE001
        load_errors.append(
            LoadError(
                code="parse_error",
                severity="Violation",
                message=str(exc),
            )
        )
        detail = _empty_fast_kpis(path)

    detail["load_errors"] = [error.to_dict() for error in load_errors]
    detail["schema_compliance"] = _skipped_schema_compliance()
    return detail


class _StreamingTripleSink:
    def __init__(self, handle):
        self._handle = handle

    def triple(self, subject, predicate, obj) -> None:
        self._handle(subject, predicate, obj)


def _parse_ntriples(path: Path, handle) -> None:
    try:
        from pyoxigraph import BlankNode as OxBlankNode
        from pyoxigraph import Literal as OxLiteral
        from pyoxigraph import NamedNode as OxNamedNode
        from pyoxigraph import parse as ox_parse
    except ImportError:
        with path.open("rb") as stream:
            W3CNTriplesParser(sink=_StreamingTripleSink(handle)).parse(stream)
        return

    def convert_term(term):
        if isinstance(term, OxNamedNode):
            return URIRef(term.value)
        if isinstance(term, OxBlankNode):
            return BNode(term.value)
        if isinstance(term, OxLiteral):
            datatype = str(term.datatype.value) if term.datatype else None
            return RDFLiteral(
                term.value,
                lang=term.language,
                datatype=URIRef(datatype) if datatype else None,
            )
        return term

    with path.open("rb") as stream:
        for triple in ox_parse(stream, "application/n-triples"):
            handle(
                convert_term(triple.subject),
                convert_term(triple.predicate),
                convert_term(triple.object),
            )


class _UnionFind:
    def __init__(self, nodes: set[URIRef]) -> None:
        self._parent = {node: node for node in nodes}
        self._size = {node: 1 for node in nodes}

    def union(self, left: URIRef, right: URIRef) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self._size[left_root] < self._size[right_root]:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        self._size[left_root] += self._size[right_root]

    def find(self, node: URIRef) -> URIRef:
        parent = self._parent[node]
        if parent != node:
            self._parent[node] = self.find(parent)
        return self._parent[node]

    def component_sizes(self) -> list[int]:
        counts: Counter[URIRef] = Counter(self.find(node) for node in self._parent)
        return sorted(counts.values(), reverse=True)


def _build_streaming_fast_kpis(
    path: Path,
    website_host: str | None,
    graph_hosts: set[str] | None,
) -> dict[str, Any]:
    uri_subjects: set[URIRef] = set()
    all_schema_urls: set[str] = set()
    entity_type_counts: Counter[str] = Counter()
    typed_subjects: set[Any] = set()
    types_by_subject: defaultdict[Any, set[str]] = defaultdict(set)
    property_counts: Counter[str] = Counter()
    predicates: set[Any] = set()
    rdf_type_triples = 0
    total_triples = 0
    property_assertions = 0

    def first_pass(subject, predicate, obj) -> None:
        nonlocal rdf_type_triples, total_triples, property_assertions
        total_triples += 1
        predicates.add(predicate)
        if isinstance(subject, URIRef):
            uri_subjects.add(subject)
        if predicate == RDF.type:
            rdf_type_triples += 1
            typed_subjects.add(subject)
            term = schema_term(obj)
            if term:
                entity_type_counts[term] += 1
                types_by_subject[subject].add(term)
            return
        property_assertions += 1
        property_counts[compact_uri(predicate)] += 1
        if predicate in {SCHEMA_URL_HTTP, SCHEMA_URL_HTTPS} and isinstance(
            obj, (RDFLiteral, URIRef)
        ):
            all_schema_urls.add(str(obj))

    _parse_ntriples(path, first_pass)

    inferred_website_host = infer_website_host(all_schema_urls)
    website_host = (website_host or inferred_website_host or "").lower() or None
    graph_hosts = (
        {host.lower() for host in graph_hosts}
        if graph_hosts
        else infer_graph_hosts(uri_subjects)
    )

    website_urls: defaultdict[str, set[str]] = defaultdict(set)
    raw_website_urls: defaultdict[str, set[str]] = defaultdict(set)
    rich_candidate_subjects: set[str] = set()
    for subject, subject_types in types_by_subject.items():
        if isinstance(subject, URIRef) and subject_types.intersection(
            RICH_RESULT_TYPES
        ):
            rich_candidate_subjects.add(str(subject))
    rich_candidate_by_type = {
        entity_type: entity_type_counts[entity_type]
        for entity_type in sorted(RICH_RESULT_TYPES)
        if entity_type_counts.get(entity_type)
    }

    internal_nodes = {
        node for node in uri_subjects if is_internal_resource(node, graph_hosts)
    }
    union_find = _UnionFind(internal_nodes)
    internal_edges_count = 0
    edge_predicates: Counter[str] = Counter()
    dangling_internal_edges: list[tuple[str, str, str]] = []
    degree: Counter[URIRef] = Counter()

    def second_pass(subject, predicate, obj) -> None:
        nonlocal internal_edges_count
        if predicate in {SCHEMA_URL_HTTP, SCHEMA_URL_HTTPS}:
            url = str(obj)
            if is_website_url(url, website_host):
                website_urls[normalize_url(url)].add(str(subject))
                if not is_ignored_duplicate_url(url):
                    raw_website_urls[url].add(str(subject))

        if (
            predicate == RDF.type
            or not isinstance(subject, URIRef)
            or not isinstance(obj, URIRef)
            or isinstance(subject, BNode)
            or isinstance(obj, BNode)
            or not is_internal_resource(subject, graph_hosts)
        ):
            return

        internal_edges_count += 1
        edge_predicates[compact_uri(predicate)] += 1
        degree[subject] += 1
        if is_internal_resource(obj, graph_hosts):
            degree[obj] += 1
            if obj in internal_nodes:
                union_find.union(subject, obj)
            if obj not in uri_subjects:
                dangling_internal_edges.append(
                    (str(subject), compact_uri(predicate), str(obj))
                )

    _parse_ntriples(path, second_pass)

    duplicate_url_groups = {
        url: sorted(subjects_for_url)
        for url, subjects_for_url in raw_website_urls.items()
        if len(subjects_for_url) > 1
        and not is_expected_homepage_identity_overlap(
            url, subjects_for_url, types_by_subject
        )
    }
    duplicate_extra_entities = sum(
        len(subjects_for_url) - 1 for subjects_for_url in duplicate_url_groups.values()
    )

    orphan_entities = sorted(
        str(node)
        for node in internal_nodes
        if node in typed_subjects and degree[node] == 0
    )
    component_sizes = union_find.component_sizes()

    return {
        "source_file": str(path),
        "scope": {
            "website_host": website_host,
            "website_host_inferred": inferred_website_host,
            "graph_hosts": sorted(graph_hosts),
        },
        "totals": {
            "total_triples": total_triples,
            "total_entity_count": len(uri_subjects),
            "total_typed_entity_count": len(typed_subjects),
            "total_property_count": property_assertions,
            "unique_property_count": len(predicates - {RDF.type}),
            "rdf_type_triples": rdf_type_triples,
            "unique_urls_within_website_scope": len(website_urls),
        },
        "entity_type_counts": dict(entity_type_counts.most_common()),
        "property_counts": dict(property_counts.most_common()),
        "rich_snippet_candidate_entities": {
            "total": len(rich_candidate_subjects),
            "by_type": rich_candidate_by_type,
        },
        "edges": {
            "total_internal_edges": internal_edges_count,
            "edge_predicate_counts": dict(edge_predicates.most_common()),
            "edge_to_node_ratio": round(internal_edges_count / len(internal_nodes), 4)
            if internal_nodes
            else 0,
        },
        "connectivity": {
            "internal_node_count": len(internal_nodes),
            "orphan_entity_count": len(orphan_entities),
            "orphan_entity_examples": orphan_entities[:25],
        },
        "integrity": {
            "broken_internal_edge_count": len(dangling_internal_edges),
            "broken_internal_edge_examples": dangling_internal_edges[:25],
            "duplicate_url_group_count": len(duplicate_url_groups),
            "duplicate_extra_entity_count": duplicate_extra_entities,
            "duplicate_url_examples": dict(list(duplicate_url_groups.items())[:25]),
        },
        "topology": {
            "isolated_graph_count": len(component_sizes),
            "largest_component_node_count": component_sizes[0]
            if component_sizes
            else 0,
            "component_size_top_10": component_sizes[:10],
        },
    }


def _empty_fast_kpis(path: Path) -> dict[str, Any]:
    return {
        "source_file": str(path),
        "scope": {
            "website_host": None,
            "website_host_inferred": None,
            "graph_hosts": [],
        },
        "totals": {
            "total_triples": 0,
            "total_entity_count": 0,
            "total_typed_entity_count": 0,
            "total_property_count": 0,
            "unique_property_count": 0,
            "rdf_type_triples": 0,
            "unique_urls_within_website_scope": 0,
        },
        "entity_type_counts": {},
        "property_counts": {},
        "rich_snippet_candidate_entities": {"total": 0, "by_type": {}},
        "edges": {
            "total_internal_edges": 0,
            "edge_predicate_counts": {},
            "edge_to_node_ratio": 0,
        },
        "connectivity": {
            "internal_node_count": 0,
            "orphan_entity_count": 0,
            "orphan_entity_examples": [],
        },
        "integrity": {
            "broken_internal_edge_count": 0,
            "broken_internal_edge_examples": [],
            "duplicate_url_group_count": 0,
            "duplicate_extra_entity_count": 0,
            "duplicate_url_examples": {},
        },
        "topology": {
            "isolated_graph_count": 0,
            "largest_component_node_count": 0,
            "component_size_top_10": [],
        },
    }


def _skipped_schema_compliance() -> dict[str, int]:
    return {
        "urls_checked": 0,
        "urls_with_errors": 0,
        "urls_with_warnings": 0,
        "errors": 0,
        "warnings": 0,
        "google_merchant_eligible": 0,
        "google_merchant_not_eligible": 0,
        "skipped": 1,
    }


def _build_schema_compliance(
    graph: Graph, opts: GraphKpiSnapshotOptions
) -> dict[str, int]:
    if opts.include_default_shapes:
        shape_specs = shape_specs_for_profile(
            opts.profile,
            builtin_shapes=opts.builtin_shapes,
            exclude_builtin_shapes=opts.exclude_builtin_shapes,
            extra_shapes=opts.extra_shapes,
        )
    else:
        shape_specs = resolve_shape_specs(
            builtin_shapes=["schemaorg-grammar"],
            exclude_builtin_shapes=["schemaorg-grammar"],
            extra_shapes=opts.extra_shapes,
        )
    normalized = _normalize_schema_org_uris(graph)
    memberships = _url_memberships(normalized, opts.subgraph_depth)
    if not memberships:
        return {
            "urls_checked": 0,
            "urls_with_errors": 0,
            "urls_with_warnings": 0,
            "errors": 0,
            "warnings": 0,
            "google_merchant_eligible": 0,
            "google_merchant_not_eligible": 0,
        }

    validation_graph = _schema_validation_graph(normalized, memberships)
    focus_urls = _focus_urls(memberships)
    main_specs = [spec for spec in shape_specs if not spec.endswith(MERCHANT_SHAPE)]
    merchant_specs = [spec for spec in shape_specs if spec.endswith(MERCHANT_SHAPE)]

    errors_by_url, warnings_by_url = _validate_shape_specs_by_url(
        validation_graph,
        main_specs,
        focus_urls,
        issue_level=opts.issue_level,
    )
    merchant_errors_by_url, _ = _validate_shape_specs_by_url(
        validation_graph,
        merchant_specs,
        focus_urls,
        issue_level="error",
    )
    by_url = sorted(memberships)
    return {
        "urls_checked": len(by_url),
        "urls_with_errors": sum(1 for url in by_url if errors_by_url[url] > 0),
        "urls_with_warnings": sum(1 for url in by_url if warnings_by_url[url] > 0),
        "errors": sum(errors_by_url.values()),
        "warnings": sum(warnings_by_url.values()),
        "google_merchant_eligible": sum(
            1 for url in by_url if merchant_errors_by_url[url] == 0
        ),
        "google_merchant_not_eligible": sum(
            1 for url in by_url if merchant_errors_by_url[url] > 0
        ),
    }


def _url_memberships(graph: Graph, depth: int) -> dict[str, set[str]]:
    all_subjects = {
        subject for subject in graph.subjects() if isinstance(subject, URIRef)
    }
    subject_index = _build_subject_index(all_subjects)
    roots_by_url: defaultdict[str, set[URIRef]] = defaultdict(set)
    for predicate in (SCHEMA_URL_HTTP, SCHEMA_URL_HTTPS):
        for subject, _, obj in graph.triples((None, predicate, None)):
            if isinstance(subject, URIRef) and isinstance(obj, (RDFLiteral, URIRef)):
                roots_by_url[str(obj)].add(subject)

    memberships: dict[str, set[str]] = {}
    for url, root_iris in roots_by_url.items():
        child_iris: set[URIRef] = set()
        for root_iri in root_iris:
            child_iris.update(
                _subjects_with_prefix(subject_index, str(root_iri).rstrip("/") + "/")
            )

        visited: set[URIRef] = set(root_iris | child_iris)
        frontier: set[URIRef] = set(visited)
        for _ in range(depth):
            next_frontier: set[URIRef] = set()
            for iri in frontier:
                for _, _, obj in graph.triples((iri, None, None)):
                    if (
                        isinstance(obj, URIRef)
                        and obj in all_subjects
                        and obj not in visited
                    ):
                        next_frontier.add(obj)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break

        for iri in set(visited) - root_iris - child_iris:
            visited.update(
                _subjects_with_prefix(subject_index, str(iri).rstrip("/") + "/")
            )

        memberships[url] = {str(iri) for iri in visited}
    return memberships


def _build_subject_index(
    all_subjects: set[URIRef],
) -> tuple[list[str], dict[str, URIRef]]:
    by_value = {str(subject): subject for subject in all_subjects}
    return sorted(by_value), by_value


def _subjects_with_prefix(
    subject_index: tuple[list[str], dict[str, URIRef]],
    prefix: str,
) -> set[URIRef]:
    ordered, by_value = subject_index
    matched: set[URIRef] = set()
    index = bisect_left(ordered, prefix)
    while index < len(ordered):
        value = ordered[index]
        if not value.startswith(prefix):
            break
        matched.add(by_value[value])
        index += 1
    return matched


def _focus_urls(memberships: dict[str, set[str]]) -> dict[str, set[str]]:
    urls_by_focus: defaultdict[str, set[str]] = defaultdict(set)
    for url, nodes in memberships.items():
        for node in nodes:
            urls_by_focus[node].add(url)
    return urls_by_focus


def _schema_validation_graph(graph: Graph, memberships: dict[str, set[str]]) -> Graph:
    included = {URIRef(value) for nodes in memberships.values() for value in nodes}
    validation_graph = Graph()
    for subject in included:
        for _, predicate, obj in graph.triples((subject, None, None)):
            if predicate != RDF.type and schema_term(predicate) is None:
                continue
            validation_graph.add((subject, predicate, obj))
    return validation_graph


def _validate_shape_specs_by_url(
    graph: Graph,
    shape_specs: list[str],
    focus_urls: dict[str, set[str]],
    *,
    issue_level: str,
) -> tuple[Counter[str], Counter[str]]:
    errors_by_url: Counter[str] = Counter()
    warnings_by_url: Counter[str] = Counter()
    if not shape_specs:
        return errors_by_url, warnings_by_url

    validator = PreparedShaclValidator.from_shape_specs(shape_specs)
    result = validator.validate_graph(graph, normalize_schema_org=False)
    for node in result.report_graph.subjects(SH.resultSeverity, None):
        if _should_skip_schemaorg_subclass_range_warning(
            report_graph=result.report_graph,
            node=node,
            source_map=validator.prepared_shapes.shape_source_map,
            data_graph=graph,
            shapes_graph=validator.prepared_shapes.shapes_graph,
        ):
            continue
        focus = result.report_graph.value(node, SH.focusNode)
        if focus is None:
            continue
        urls = focus_urls.get(str(focus))
        if not urls:
            continue
        severity = result.report_graph.value(node, SH.resultSeverity)
        target = errors_by_url if severity == SH.Violation else warnings_by_url
        if severity != SH.Violation and issue_level == "error":
            continue
        for url in urls:
            target[url] += 1
    return errors_by_url, warnings_by_url


def _numeric_only(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid API KPI payload values.")
    if isinstance(value, (int, float)):
        if value < 0 or value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(
                "API KPI payload values must be finite non-negative numbers."
            )
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if key in {"snapshot_date", "calculated_at", "snapshot_origin"}:
                result[key] = child
                continue
            result[str(key)] = _numeric_only(child)
        return result
    raise ValueError(
        f"API KPI payload value must be numeric or nested numeric object: {value!r}"
    )


__all__ = [
    "GraphKpiSnapshotOptions",
    "build_graph_kpi_api_payload",
    "calculate_graph_kpi_snapshot",
]

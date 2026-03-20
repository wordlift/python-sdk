"""Public utility: build_entity_matrix — URL × entity-type pivot table."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rdflib import RDF, Graph, URIRef

from wordlift_sdk.graph.audit._loader import load_graph
from wordlift_sdk.graph.audit.kpis.schema_compliance import (
    _build_subgraph,
    _find_webpage_urls,
)
from wordlift_sdk.validation.shacl import (
    _normalize_schema_org_uris as normalize_schema_org_uris,  # type: ignore[attr-defined]
)

_SCHEMA_ORG_PREFIXES = ("http://schema.org/", "https://schema.org/")


def _short_type_name(type_iri: str) -> str:
    """Return a short type name from a full IRI."""
    for prefix in _SCHEMA_ORG_PREFIXES:
        if type_iri.startswith(prefix):
            return type_iri[len(prefix) :]
    for sep in ("#", "/"):
        idx = type_iri.rfind(sep)
        if idx >= 0:
            return type_iri[idx + 1 :]
    return type_iri


def _parent_path(url: str) -> str:
    """Return the parent path of a URL (last path segment removed)."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    netloc = f"{parsed.scheme}://{parsed.netloc}"
    return f"{netloc}{parent}"


def _count_types(subgraph: Graph, exclude_types: set[str]) -> dict[str, int]:
    """Count entity types in a subgraph, returning short-name → count."""
    counts: dict[str, int] = defaultdict(int)
    for _, _, type_iri in subgraph.triples((None, RDF.type, None)):
        if isinstance(type_iri, URIRef):
            short = _short_type_name(str(type_iri))
            if short not in exclude_types:
                counts[short] += 1
    return dict(counts)


def _cluster_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cluster rows by parent path + type signature per the spec."""
    by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_parent[_parent_path(row["url"])].append(row)

    result: list[dict[str, Any]] = []
    for parent, group in by_parent.items():
        by_sig: dict[frozenset, list[dict[str, Any]]] = defaultdict(list)
        for row in group:
            sig = frozenset(k for k, v in row.items() if k != "url" and v > 0)
            by_sig[sig].append(row)

        for sub_group in by_sig.values():
            if len(sub_group) >= 2:
                wildcard_url = f"{parent}/*"
                merged: dict[str, Any] = {"url": wildcard_url}
                for row in sub_group:
                    for k, v in row.items():
                        if k != "url":
                            merged[k] = merged.get(k, 0) + v
                result.append(merged)
            else:
                result.extend(sub_group)

    return result


def build_entity_matrix(
    path: str | Path,
    *,
    exclude_types: list[str] | None = None,
    cluster: bool = False,
    subgraph_depth: int = 1,
) -> list[dict[str, Any]]:
    """
    Build a URL × entity-type pivot table from a graph file.

    Returns a list of dicts — one per URL (or URL cluster when *cluster* is
    ``True``) — with the structure::

        {"url": "https://example.com/article", "Article": 1, "Thing": 2}

    * ``url`` is the ``schema:url`` value of the page entity.
    * All other keys are short type names: the ``http(s)://schema.org/``
      prefix is stripped; for other namespaces the local name after ``#``
      or ``/`` is used.
    * Values are integer counts of entities of that type in the URL's
      subgraph (``0`` when absent).
    * Type columns are sorted alphabetically; rows are sorted by URL.

    Parameters
    ----------
    path:
        Path to the RDF file to load.
    exclude_types:
        Short type names to omit entirely from both rows and columns.
    cluster:
        When ``True``, collapse URL sub-groups that share the same parent
        path **and** type signature (≥ 2 URLs) into a single wildcard row
        whose ``url`` is ``<parent_path>/*`` and whose counts are summed.
    subgraph_depth:
        Number of relationship hops when assembling each URL's subgraph.
    """
    excl: set[str] = set(exclude_types or [])

    load_result = load_graph(path)
    normalized = normalize_schema_org_uris(load_result.graph)
    webpage_urls = _find_webpage_urls(normalized)

    if not webpage_urls:
        return []

    all_subjects = {s for s in normalized.subjects() if isinstance(s, URIRef)}

    rows: list[dict[str, Any]] = []
    for url in sorted(webpage_urls):
        subgraph = _build_subgraph(normalized, url, subgraph_depth, all_subjects)
        counts = _count_types(subgraph, excl)
        row: dict[str, Any] = {"url": url}
        row.update(counts)
        rows.append(row)

    if cluster:
        rows = _cluster_rows(rows)

    # Collect all type columns
    all_types: set[str] = set()
    for row in rows:
        all_types.update(k for k in row if k != "url")
    sorted_types = sorted(all_types)

    # Fill missing columns with 0, sort rows by URL
    result: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: r["url"]):
        d: dict[str, Any] = {"url": row["url"]}
        for t in sorted_types:
            d[t] = row.get(t, 0)
        result.append(d)

    return result


__all__ = ["build_entity_matrix"]

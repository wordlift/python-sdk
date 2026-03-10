"""KPI: duplicate entities sharing the same schema:url."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rdflib import Graph, Literal, URIRef

_SCHEMA_URL_HTTP = URIRef("http://schema.org/url")
_SCHEMA_URL_HTTPS = URIRef("https://schema.org/url")


@dataclass(frozen=True)
class DuplicatesResult:
    count: int
    groups: list[list[str]]

    def to_dict(self) -> dict:
        return {"duplicates": {"count": self.count, "groups": self.groups}}


class DuplicatesKpi:
    """Find distinct entity IRIs sharing the same schema:url value."""

    def collect(self, graph: Graph) -> DuplicatesResult:
        url_to_iris: defaultdict[str, set[str]] = defaultdict(set)
        for pred in (_SCHEMA_URL_HTTP, _SCHEMA_URL_HTTPS):
            for s, _, o in graph.triples((None, pred, None)):
                if isinstance(s, URIRef) and isinstance(o, (URIRef, Literal)):
                    url_to_iris[str(o)].add(str(s))
        groups = [sorted(iris) for iris in url_to_iris.values() if len(iris) > 1]
        groups.sort()
        return DuplicatesResult(count=len(groups), groups=groups)


__all__ = ["DuplicatesKpi", "DuplicatesResult"]

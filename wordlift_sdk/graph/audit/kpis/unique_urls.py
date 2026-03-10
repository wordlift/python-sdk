"""KPI: unique schema:url values."""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import Graph, Literal, URIRef

_SCHEMA_URL_HTTP = URIRef("http://schema.org/url")
_SCHEMA_URL_HTTPS = URIRef("https://schema.org/url")


@dataclass(frozen=True)
class UniqueUrlsResult:
    count: int
    urls: list[str]

    def to_dict(self) -> dict:
        return {"unique_urls": {"count": self.count, "urls": self.urls}}


class UniqueUrlsKpi:
    """Collect distinct schema:url values across the graph."""

    def collect(self, graph: Graph) -> UniqueUrlsResult:
        seen: set[str] = set()
        for pred in (_SCHEMA_URL_HTTP, _SCHEMA_URL_HTTPS):
            for _, _, o in graph.triples((None, pred, None)):
                if isinstance(o, (URIRef, Literal)):
                    seen.add(str(o))
        urls = sorted(seen)
        return UniqueUrlsResult(count=len(urls), urls=urls)


__all__ = ["UniqueUrlsKpi", "UniqueUrlsResult"]

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
from rdflib import Graph, Literal, URIRef

SCHEMA = "http://schema.org/"


class IriLookup(Protocol):
    """Resolve a preferred IRI for a subject in the current graph."""

    def iri_for_subject(self, graph: Graph, subject: URIRef) -> str | None: ...


def normalize_url(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    try:
        split = urlsplit(text)
    except Exception:
        return text
    scheme = split.scheme.lower()
    netloc = split.netloc.lower()
    path = split.path
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    query = parse_qsl(split.query, keep_blank_values=True)
    query.sort()
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def iri_path_depth(iri: str) -> int:
    try:
        split = urlsplit(iri)
        return len([segment for segment in split.path.split("/") if segment])
    except Exception:
        return 10**9


@dataclass(frozen=True)
class DataFrameUrlIriLookup:
    """Resolve subject IRIs from a URL->IRI dataframe."""

    df: pd.DataFrame
    url_column: str = "url"
    iri_column: str = "iri"

    def __post_init__(self) -> None:
        for column in (self.url_column, self.iri_column):
            if column not in self.df.columns:
                raise ValueError(f"Missing required dataframe column: {column}")

        by_url: dict[str, tuple[str, int, int]] = {}
        for index, row in self.df.iterrows():
            raw_url = row.get(self.url_column)
            raw_iri = row.get(self.iri_column)
            if pd.isna(raw_url) or pd.isna(raw_iri):
                continue
            normalized_url = normalize_url(str(raw_url))
            iri = str(raw_iri).strip()
            if not normalized_url or not iri:
                continue

            depth = iri_path_depth(iri)
            candidate = (iri, depth, int(index))
            current = by_url.get(normalized_url)
            if current is None:
                by_url[normalized_url] = candidate
                continue
            if (candidate[1], len(candidate[0]), candidate[2]) < (
                current[1],
                len(current[0]),
                current[2],
            ):
                by_url[normalized_url] = candidate

        object.__setattr__(
            self,
            "_url_to_iri",
            {url: value[0] for url, value in by_url.items()},
        )

    def iri_for_subject(self, graph: Graph, subject: URIRef) -> str | None:
        url = self._subject_url(graph, subject)
        if not url:
            return None
        return self._url_to_iri.get(normalize_url(url))

    @staticmethod
    def _subject_url(graph: Graph, subject: URIRef) -> str | None:
        value = graph.value(subject, URIRef(f"{SCHEMA}url"))
        if isinstance(value, (Literal, URIRef)):
            text = str(value).strip()
            if text:
                return text
        return None

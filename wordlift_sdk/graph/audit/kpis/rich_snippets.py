"""KPI: entities eligible for Google rich snippets."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from pyshacl import validate
from rdflib import Graph, RDF, URIRef
from rdflib.namespace import SH

from wordlift_sdk.validation.shacl import (
    _load_shapes_graph,  # type: ignore[attr-defined]
    _normalize_schema_org_uris,  # type: ignore[attr-defined]
)

_MERCHANT_SHAPE = "google-merchant-listing.ttl"


@dataclass(frozen=True)
class RichSnippetsResult:
    eligible_valid: dict[str, int] | dict[str, list[str]]
    eligible_invalid: dict[str, int] | dict[str, list[str]]

    def to_dict(self) -> dict:
        return {
            "rich_snippets": {
                "eligible_valid": self.eligible_valid,
                "eligible_invalid": self.eligible_invalid,
            }
        }


class RichSnippetsKpi:
    """
    Classify entities by rich-snippet eligibility.

    eligible_valid  – entity type is targeted by a Google SHACL shape AND passes.
    eligible_invalid – entity type is targeted by a Google SHACL shape AND fails.

    granularity='counts' (default): returns {type_iri: count}
    granularity='entities': returns {type_iri: [iri, ...]}
    """

    def __init__(
        self,
        granularity: Literal["counts", "entities"] = "counts",
    ) -> None:
        self._granularity = granularity

    def collect(self, graph: Graph) -> RichSnippetsResult:
        normalized = _normalize_schema_org_uris(graph)

        # Load all Google shapes (excluding merchant — handled separately in schema_compliance)
        all_google_specs = [
            s for s in _google_shape_specs() if not s.endswith(_MERCHANT_SHAPE)
        ]
        if not all_google_specs:
            return RichSnippetsResult(eligible_valid={}, eligible_invalid={})

        shapes_graph, _ = _load_shapes_graph(all_google_specs)

        # Determine which rdf:type values are targeted by at least one shape
        targeted_types: set[str] = {
            str(o) for _, _, o in shapes_graph.triples((None, SH.targetClass, None))
        }
        if not targeted_types:
            return RichSnippetsResult(eligible_valid={}, eligible_invalid={})

        # Find entities whose type is targeted
        entity_types: dict[str, set[str]] = defaultdict(set)  # iri → types
        for s, _, o in normalized.triples((None, RDF.type, None)):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                t = str(o)
                if t in targeted_types:
                    entity_types[str(s)].add(t)

        if not entity_types:
            return RichSnippetsResult(eligible_valid={}, eligible_invalid={})

        # Run SHACL once on the whole normalized graph
        _, report_graph, _ = validate(
            normalized,
            shacl_graph=shapes_graph,
            inference="rdfs",
            abort_on_first=False,
            allow_infos=True,
            allow_warnings=True,
        )

        # Collect focus nodes that have at least one Violation
        violated: set[str] = set()
        for node in report_graph.subjects(SH.resultSeverity, SH.Violation):
            focus = report_graph.value(node, SH.focusNode)
            if focus is not None:
                violated.add(str(focus))

        # Split entities into valid / invalid per type
        valid: defaultdict[str, list[str]] = defaultdict(list)
        invalid: defaultdict[str, list[str]] = defaultdict(list)
        for iri, types in sorted(entity_types.items()):
            bucket = invalid if iri in violated else valid
            for t in types:
                bucket[t].append(iri)

        if self._granularity == "counts":
            return RichSnippetsResult(
                eligible_valid={t: len(iris) for t, iris in sorted(valid.items())},
                eligible_invalid={t: len(iris) for t, iris in sorted(invalid.items())},
            )
        return RichSnippetsResult(
            eligible_valid={t: sorted(iris) for t, iris in sorted(valid.items())},
            eligible_invalid={t: sorted(iris) for t, iris in sorted(invalid.items())},
        )


def _google_shape_specs() -> list[str]:
    """Return bundled shape names that start with 'google-'."""
    from importlib import resources

    shapes_dir = resources.files("wordlift_sdk.validation.shacls")
    return [
        entry.name
        for entry in shapes_dir.iterdir()
        if entry.is_file()
        and entry.name.endswith(".ttl")
        and entry.name.startswith("google-")
    ]


__all__ = ["RichSnippetsKpi", "RichSnippetsResult"]

"""KPI: entities eligible for Google rich snippets."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from rdflib import Graph, RDF, URIRef
from rdflib.namespace import SH

from wordlift_sdk.validation.shacl import (
    _normalize_schema_org_uris,  # type: ignore[attr-defined]
    PreparedShapes,
    PreparedShaclValidator,
    prepare_shapes,
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


@dataclass(frozen=True)
class RichSnippetsValidationSummary:
    entity_types: dict[str, tuple[str, ...]]
    invalid_entities: frozenset[str]


class RichSnippetsKpi:
    """
    Classify entities by rich-snippet eligibility.

    eligible_valid  – entity type is a root Google rich-result target AND passes.
    eligible_invalid – entity type is a root Google rich-result target AND fails.

    granularity='counts' (default): returns {type_iri: count}
    granularity='entities': returns {type_iri: [iri, ...]}
    """

    def __init__(
        self,
        granularity: Literal["counts", "entities"] = "counts",
    ) -> None:
        self._granularity = granularity
        self._prepared_shapes = _prepare_google_shapes()

    def collect(self, graph: Graph) -> RichSnippetsResult:
        normalized = _normalize_schema_org_uris(graph)
        if not self._prepared_shapes.shape_specs:
            return RichSnippetsResult(eligible_valid={}, eligible_invalid={})

        validator = PreparedShaclValidator(self._prepared_shapes)
        validation = validator.validate_graph(normalized, normalize_schema_org=False)
        summary = build_rich_snippets_validation_summary(
            normalized,
            validation.report_graph,
            validator.prepared_shapes.shape_source_map,
        )
        return self.collect_from_summary(summary)

    def collect_from_summary(
        self, summary: RichSnippetsValidationSummary
    ) -> RichSnippetsResult:
        valid: defaultdict[str, list[str]] = defaultdict(list)
        invalid: defaultdict[str, list[str]] = defaultdict(list)

        for iri, types in sorted(summary.entity_types.items()):
            bucket = invalid if iri in summary.invalid_entities else valid
            for type_iri in types:
                bucket[type_iri].append(iri)

        if self._granularity == "counts":
            return RichSnippetsResult(
                eligible_valid={t: len(iris) for t, iris in sorted(valid.items())},
                eligible_invalid={t: len(iris) for t, iris in sorted(invalid.items())},
            )

        return RichSnippetsResult(
            eligible_valid={t: sorted(iris) for t, iris in sorted(valid.items())},
            eligible_invalid={t: sorted(iris) for t, iris in sorted(invalid.items())},
        )


def build_rich_snippets_validation_summary(
    graph: Graph,
    report_graph: Graph,
    shape_source_map: dict,
) -> RichSnippetsValidationSummary:
    targeted_types = _targeted_google_types(_prepare_google_shapes())
    entity_types = _collect_targeted_entity_types(graph, targeted_types)
    invalid_entities = _google_invalid_focus_nodes(report_graph, shape_source_map)
    return RichSnippetsValidationSummary(
        entity_types={
            iri: tuple(sorted(types)) for iri, types in sorted(entity_types.items())
        },
        invalid_entities=frozenset(invalid_entities),
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


def _prepare_google_shapes() -> PreparedShapes:
    all_google_specs = [
        spec for spec in _google_shape_specs() if not spec.endswith(_MERCHANT_SHAPE)
    ]
    if not all_google_specs:
        return PreparedShapes(
            shape_specs=tuple(), shapes_graph=Graph(), shape_source_map={}
        )
    return prepare_shapes(all_google_specs)


def _targeted_google_types(prepared_shapes: PreparedShapes) -> set[str]:
    targeted_types: set[str] = {
        str(obj)
        for _, _, obj in prepared_shapes.shapes_graph.triples(
            (None, SH.targetClass, None)
        )
    }
    targeted_types -= _helper_only_target_types()
    return targeted_types


def _collect_targeted_entity_types(
    graph: Graph, targeted_types: set[str]
) -> dict[str, set[str]]:
    entity_types: dict[str, set[str]] = defaultdict(set)
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        if isinstance(subject, URIRef) and isinstance(obj, URIRef):
            type_iri = str(obj)
            if type_iri in targeted_types:
                entity_types[str(subject)].add(type_iri)
    return entity_types


def _google_invalid_focus_nodes(
    report_graph: Graph,
    shape_source_map: dict,
) -> set[str]:
    invalid_entities: set[str] = set()
    for node in report_graph.subjects(SH.resultSeverity, SH.Violation):
        source_shape = report_graph.value(node, SH.sourceShape)
        if source_shape is None:
            continue
        source_label = shape_source_map.get(source_shape) or shape_source_map.get(
            str(source_shape)
        )
        if not isinstance(source_label, str):
            continue
        if (
            not source_label.startswith("google-")
            or source_label == "google-merchant-listing"
        ):
            continue
        focus = report_graph.value(node, SH.focusNode)
        if focus is not None:
            invalid_entities.add(str(focus))
    return invalid_entities


def _helper_only_target_types() -> set[str]:
    """Return bundled Google target classes that are helper-only, not root results."""

    helper_names = {
        "3DModel",
        "BroadcastEvent",
        "Certification",
        "Clip",
        "Conditions",
        "DataDownload",
        "DefinedRegion",
        "HowToDirection",
        "HowToSection",
        "HowToTip",
        "InteractionCounter",
        "MonetaryAmount",
        "Offer",
        "OfferShippingDetails",
        "OpeningHoursSpecification",
        "PeopleAudience",
        "QuantitativeValue",
        "Rating",
        "SeekToAction",
        "ServicePeriod",
        "ShippingConditions",
        "ShippingDeliveryTime",
        "ShippingRateSettings",
        "ShippingService",
        "SizeSpecification",
        "UnitPriceSpecification",
    }
    return {f"http://schema.org/{name}" for name in helper_names}


__all__ = [
    "RichSnippetsKpi",
    "RichSnippetsResult",
    "RichSnippetsValidationSummary",
    "build_rich_snippets_validation_summary",
]

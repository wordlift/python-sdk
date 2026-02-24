from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from rdflib import Graph, RDF, URIRef


@dataclass
class KgBuildKpiCollector:
    """Aggregate run-level graph sync KPIs for dataset-scoped entities."""

    dataset_uri: str | None
    run_id: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _entities: set[str] = field(default_factory=set, init=False)
    _type_assertions_total: int = field(default=0, init=False)
    _property_assertions_total: int = field(default=0, init=False)
    _entities_by_type: defaultdict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set), init=False
    )
    _properties_by_predicate: Counter[str] = field(default_factory=Counter, init=False)
    _validation_total: int = field(default=0, init=False)
    _validation_pass: int = field(default=0, init=False)
    _validation_fail: int = field(default=0, init=False)
    _warning_count: int = field(default=0, init=False)
    _error_count: int = field(default=0, init=False)
    _warning_sources: Counter[str] = field(default_factory=Counter, init=False)
    _error_sources: Counter[str] = field(default_factory=Counter, init=False)

    def graph_metrics(self, graph: Graph) -> dict[str, int]:
        if not self.dataset_uri:
            return {
                "entities": 0,
                "type_assertions": 0,
                "property_assertions": 0,
            }
        prefix = str(self.dataset_uri).rstrip("/")
        if not prefix:
            return {
                "entities": 0,
                "type_assertions": 0,
                "property_assertions": 0,
            }
        subjects = {
            str(subject)
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(prefix)
        }
        type_assertions = 0
        property_assertions = 0
        for subject, predicate, _ in graph:
            if str(subject) not in subjects:
                continue
            if predicate == RDF.type:
                type_assertions += 1
            else:
                property_assertions += 1
        return {
            "entities": len(subjects),
            "type_assertions": type_assertions,
            "property_assertions": property_assertions,
        }

    def record_graph(self, graph: Graph) -> None:
        if not self.dataset_uri:
            return
        prefix = str(self.dataset_uri).rstrip("/")
        if not prefix:
            return

        subjects = {
            str(subject)
            for subject in graph.subjects()
            if isinstance(subject, URIRef) and str(subject).startswith(prefix)
        }
        if not subjects:
            return

        self._entities.update(subjects)

        for subject, predicate, obj in graph:
            subject_s = str(subject)
            if subject_s not in subjects:
                continue

            if predicate == RDF.type:
                self._type_assertions_total += 1
                self._entities_by_type[str(obj)].add(subject_s)
                continue

            self._property_assertions_total += 1
            self._properties_by_predicate[str(predicate)] += 1

    def record_validation(
        self,
        *,
        passed: bool,
        warning_count: int,
        error_count: int,
        warning_sources: dict[str, int] | Counter[str] | None = None,
        error_sources: dict[str, int] | Counter[str] | None = None,
    ) -> None:
        self._validation_total += 1
        if passed:
            self._validation_pass += 1
        else:
            self._validation_fail += 1
        self._warning_count += warning_count
        self._error_count += error_count
        if warning_sources:
            self._warning_sources.update(warning_sources)
        if error_sources:
            self._error_sources.update(error_sources)

    def summary(self, profile_name: str) -> dict[str, object]:
        entities_by_type = {
            type_iri: len(entities)
            for type_iri, entities in sorted(self._entities_by_type.items())
        }
        properties_by_predicate = dict(
            sorted(self._properties_by_predicate.items(), key=lambda item: item[0])
        )
        return {
            "run_id": self.run_id,
            "profile": profile_name,
            "totals": {
                "total_entities": len(self._entities),
                "type_assertions_total": self._type_assertions_total,
                "property_assertions_total": self._property_assertions_total,
            },
            "entities_by_type": entities_by_type,
            "properties_by_predicate": properties_by_predicate,
            "validation": {
                "total": self._validation_total,
                "pass": self._validation_pass,
                "fail": self._validation_fail,
                "warnings": {
                    "count": self._warning_count,
                    "sources": dict(
                        sorted(self._warning_sources.items(), key=lambda item: item[0])
                    ),
                },
                "errors": {
                    "count": self._error_count,
                    "sources": dict(
                        sorted(self._error_sources.items(), key=lambda item: item[0])
                    ),
                },
            },
        }

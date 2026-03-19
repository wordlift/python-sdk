from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rdflib import Graph, Literal, RDF, URIRef

from ...id_policy import DEFAULT_ID_POLICY, IdPolicy

SCHEMA = "http://schema.org/"


def normalize_slug(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^\w\s-]", " ", lowered)
    lowered = re.sub(r"[_\s]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "thing"


class IdAllocator:
    """Allocate canonical IRIs for postprocessors using shared ID policy."""

    def __init__(self, dataset_uri: str, policy: IdPolicy | None = None) -> None:
        self.dataset_uri = dataset_uri.rstrip("/")
        self.policy = policy or DEFAULT_ID_POLICY

    def assign(
        self,
        graph: Graph,
        subject: URIRef | None = None,
        *,
        parent: URIRef | None = None,
        type_name: str | None = None,
        base_value: str | None = None,
        index: int | None = None,
        force_index: bool = False,
        url_value: str | None = None,
        rewrite: bool = True,
    ) -> URIRef:
        if subject is None:
            return self.new(
                graph,
                parent=parent,
                type_name=type_name,
                base_value=base_value,
                index=index,
                force_index=force_index,
                url_value=url_value,
            )

        resolved_type = self._resolve_type_name(graph, subject, type_name)

        gtin = self._first_value(graph, subject, "gtin")
        if gtin:
            new_iri = URIRef(f"{self.dataset_uri}/01/{normalize_slug(gtin)}")
            if rewrite:
                self._swap_iri(graph, subject, new_iri)
            return new_iri

        if parent is not None:
            new_iri = self.child(
                graph,
                subject,
                parent=parent,
                type_name=resolved_type,
                base_value=base_value,
                index=index,
                force_index=force_index,
                url_value=url_value,
                rewrite=rewrite,
            )
            return new_iri

        return self.independent(
            graph,
            subject,
            type_name=resolved_type,
            base_value=base_value,
            index=index,
            force_index=force_index,
            url_value=url_value,
            rewrite=rewrite,
        )

    def new(
        self,
        graph: Graph,
        *,
        parent: URIRef | None = None,
        type_name: str | None = None,
        base_value: str | None = None,
        index: int | None = None,
        force_index: bool = False,
        url_value: str | None = None,
    ) -> URIRef:
        if parent is not None:
            return self.new_child(
                graph,
                parent=parent,
                type_name=type_name,
                base_value=base_value,
                index=index,
                force_index=force_index,
                url_value=url_value,
            )
        return self.new_independent(
            graph,
            type_name=type_name,
            base_value=base_value,
            index=index,
            force_index=force_index,
            url_value=url_value,
        )

    def new_independent(
        self,
        graph: Graph,
        *,
        type_name: str | None = None,
        base_value: str | None = None,
        index: int | None = None,
        force_index: bool = False,
        url_value: str | None = None,
    ) -> URIRef:
        resolved_type = self.policy.normalize_type_name(type_name or "Thing")
        container = self.policy.container_for_type(resolved_type)
        entity_id = self._entity_id(
            graph,
            None,
            type_name=resolved_type,
            base_value=base_value,
            index=index,
            force_index=force_index,
            url_value=url_value,
            path_prefix=f"{self.dataset_uri}/{container}/",
        )
        return URIRef(f"{self.dataset_uri}/{container}/{entity_id}")

    def new_child(
        self,
        graph: Graph,
        *,
        parent: URIRef,
        type_name: str | None = None,
        base_value: str | None = None,
        index: int | None = None,
        force_index: bool = False,
        url_value: str | None = None,
    ) -> URIRef:
        resolved_type = self.policy.normalize_type_name(type_name or "Thing")
        container = self.policy.container_for_type(resolved_type)
        prefix = f"{parent}/{container}/"
        entity_id = self._entity_id(
            graph,
            None,
            type_name=resolved_type,
            base_value=base_value,
            index=index,
            force_index=force_index,
            url_value=url_value,
            path_prefix=prefix,
        )
        return URIRef(f"{prefix}{entity_id}")

    def independent(
        self,
        graph: Graph,
        subject: URIRef,
        *,
        type_name: str | None = None,
        base_value: str | None = None,
        index: int | None = None,
        force_index: bool = False,
        url_value: str | None = None,
        rewrite: bool = True,
    ) -> URIRef:
        resolved_type = self._resolve_type_name(graph, subject, type_name)
        container = self.policy.container_for_type(resolved_type)
        entity_id = self._entity_id(
            graph,
            subject,
            type_name=resolved_type,
            base_value=base_value,
            index=index,
            force_index=force_index,
            url_value=url_value,
            path_prefix=f"{self.dataset_uri}/{container}/",
        )
        new_iri = URIRef(f"{self.dataset_uri}/{container}/{entity_id}")
        if rewrite:
            self._swap_iri(graph, subject, new_iri)
        return new_iri

    def child(
        self,
        graph: Graph,
        subject: URIRef,
        *,
        parent: URIRef,
        type_name: str | None = None,
        base_value: str | None = None,
        index: int | None = None,
        force_index: bool = False,
        url_value: str | None = None,
        rewrite: bool = True,
    ) -> URIRef:
        resolved_type = self._resolve_type_name(graph, subject, type_name)
        container = self.policy.container_for_type(resolved_type)
        prefix = f"{parent}/{container}/"
        entity_id = self._entity_id(
            graph,
            subject,
            type_name=resolved_type,
            base_value=base_value,
            index=index,
            force_index=force_index,
            url_value=url_value,
            path_prefix=prefix,
        )
        new_iri = URIRef(f"{prefix}{entity_id}")
        if rewrite:
            self._swap_iri(graph, subject, new_iri)
        return new_iri

    def _entity_id(
        self,
        graph: Graph,
        subject: URIRef | None,
        *,
        type_name: str,
        base_value: str | None,
        index: int | None,
        force_index: bool,
        url_value: str | None,
        path_prefix: str,
    ) -> str:
        raw_base = (
            base_value
            or self._base_from_priority(graph, subject)
            or self.policy.normalize_type_name(type_name)
            or "Thing"
        )
        base_slug = normalize_slug(raw_base)
        resolved_url = url_value or self._first_value(graph, subject, "url")
        if resolved_url:
            return f"{base_slug}-{self._url_hash(resolved_url)}"
        if force_index and index is not None:
            return f"{base_slug}-{index}"

        candidate = base_slug
        if subject is not None and URIRef(f"{path_prefix}{candidate}") == subject:
            return candidate
        if any(str(s) == f"{path_prefix}{candidate}" for s in graph.subjects()):
            next_index = 2
            while any(
                str(s) == f"{path_prefix}{base_slug}-{next_index}"
                for s in graph.subjects()
            ):
                next_index += 1
            return f"{base_slug}-{next_index}"
        return candidate

    def _resolve_type_name(
        self,
        graph: Graph,
        subject: URIRef | None,
        type_name: str | None,
    ) -> str:
        if type_name:
            return self.policy.normalize_type_name(type_name)
        if subject is None:
            return self.policy.normalize_type_name("Thing")
        discovered = self._type_name_or_thing(graph, subject)
        return self.policy.normalize_type_name(discovered)

    @staticmethod
    def _type_name_or_thing(graph: Graph, subject: URIRef) -> str:
        for obj in graph.objects(subject, RDF.type):
            if isinstance(obj, URIRef) and str(obj).startswith(SCHEMA):
                return str(obj).split("/")[-1]
        return "Thing"

    @staticmethod
    def _first_value(
        graph: Graph, subject: URIRef | None, *predicate_suffixes: str
    ) -> str | None:
        if subject is None:
            return None
        for suffix in predicate_suffixes:
            value = graph.value(subject, URIRef(f"{SCHEMA}{suffix}"))
            if isinstance(value, (Literal, URIRef)):
                text = str(value).strip()
                if text:
                    return text
        return None

    @staticmethod
    def _base_from_priority(graph: Graph, subject: URIRef | None) -> str | None:
        if subject is None:
            return None
        predicates = ("name", "headline", "title", "gtin", "sku", "value")
        for pred in predicates:
            value = graph.value(subject, URIRef(f"{SCHEMA}{pred}"))
            if isinstance(value, (Literal, URIRef)):
                text = str(value).strip()
                if text:
                    return text
        return None

    @staticmethod
    def _url_hash(value: str) -> str:
        try:
            split = urlsplit(value)
            query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
            normalized = urlunsplit((split.scheme, split.netloc, split.path, query, ""))
        except Exception:
            normalized = value
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _swap_iri(graph: Graph, old_iri: URIRef, new_iri: URIRef) -> None:
        if old_iri == new_iri:
            return
        for subject, predicate, obj in list(graph.triples((old_iri, None, None))):
            graph.remove((subject, predicate, obj))
            graph.add((new_iri, predicate, obj))
        for subject, predicate, obj in list(graph.triples((None, None, old_iri))):
            graph.remove((subject, predicate, obj))
            graph.add((subject, predicate, new_iri))

from __future__ import annotations

from collections import defaultdict
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rdflib import Graph, Literal, RDF, URIRef

from .id_policy import DEFAULT_ID_POLICY, IdPolicy

SCHEMA = "http://schema.org/"


def normalize_slug(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^\w\s-]", " ", lowered)
    lowered = re.sub(r"[_\s]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "thing"


class CanonicalIdGenerator:
    """Pure graph-ID canonicalization logic."""

    def __init__(self, policy: IdPolicy | None = None) -> None:
        self._policy = policy or DEFAULT_ID_POLICY

    def apply(self, graph: Graph, dataset_uri: str) -> Graph:
        dataset_uri = dataset_uri.rstrip("/")
        if not dataset_uri:
            return graph

        self._rewrite_pages_and_children(graph, dataset_uri)
        self._rewrite_entity_roots(graph, dataset_uri)
        return graph

    def _rewrite_pages_and_children(self, graph: Graph, dataset_uri: str) -> None:
        page_nodes = {
            subject
            for subject in graph.subjects()
            if self._has_page_root_type(graph, subject)
        }

        for old_page in sorted(page_nodes, key=str):
            url = graph.value(old_page, URIRef(f"{SCHEMA}url"))
            page_slug = self._entity_slug(
                graph,
                old_page,
                default_base="web-page",
                url_value=str(url) if isinstance(url, (Literal, URIRef)) else None,
            )
            new_page = URIRef(
                f"{dataset_uri}/{self._policy.container_for_type('WebPage')}/{page_slug}"
            )
            self._swap_iri(graph, old_page, new_page)
            self._rewrite_faq(graph, new_page)
            self._rewrite_videos(graph, new_page)
            self._rewrite_images(graph, new_page)
            self._rewrite_howto(graph, new_page)

    def _rewrite_faq(self, graph: Graph, page_iri: URIRef) -> None:
        faq_nodes: set[URIRef] = set()
        for obj in graph.objects(page_iri, URIRef(f"{SCHEMA}hasPart")):
            if isinstance(obj, URIRef) and self._is_typed_as(graph, obj, "FAQPage"):
                faq_nodes.add(obj)
        for subject in graph.subjects(RDF.type, URIRef(f"{SCHEMA}FAQPage")):
            faq_nodes.add(subject)

        for idx, faq in enumerate(sorted(faq_nodes, key=str), start=1):
            suffix = "" if len(faq_nodes) == 1 else f"-{idx}"
            faq_container = self._policy.container_for_type("FAQPage")
            new_faq = URIRef(f"{page_iri}/{faq_container}/faq-page{suffix}")
            self._swap_iri(graph, faq, new_faq)

            questions = set(graph.objects(new_faq, URIRef(f"{SCHEMA}mainEntity")))
            for subject in graph.subjects(RDF.type, URIRef(f"{SCHEMA}Question")):
                if str(subject).startswith(str(new_faq)):
                    questions.add(subject)

            for q_idx, question in enumerate(sorted(questions, key=str), start=1):
                question_slug = self._entity_slug(
                    graph,
                    question,
                    default_base="question",
                    url_value=None,
                    index=q_idx,
                    force_index=len(questions) > 1,
                )
                q_container = self._policy.container_for_type("Question")
                new_question = URIRef(f"{new_faq}/{q_container}/{question_slug}")
                self._swap_iri(graph, question, new_question)

                answer = graph.value(new_question, URIRef(f"{SCHEMA}acceptedAnswer"))
                if answer is not None:
                    a_container = self._policy.container_for_type("Answer")
                    new_answer = URIRef(f"{new_question}/{a_container}/answer-1")
                    self._swap_iri(graph, answer, new_answer)

    def _rewrite_videos(self, graph: Graph, page_iri: URIRef) -> None:
        videos: set[URIRef] = set()
        for obj in graph.objects(page_iri, URIRef(f"{SCHEMA}video")):
            if isinstance(obj, URIRef) and (
                self._is_typed_as(graph, obj, "VideoObject")
                or self._is_local_dependent_node(obj, page_iri)
            ):
                videos.add(obj)
        for subject in graph.subjects(RDF.type, URIRef(f"{SCHEMA}VideoObject")):
            if str(subject).startswith(str(page_iri)):
                videos.add(subject)

        for idx, video in enumerate(sorted(videos, key=str), start=1):
            video_slug = self._entity_slug(
                graph,
                video,
                default_base="video-object",
                url_value=self._first_value(graph, video, "embedUrl", "contentUrl"),
                index=idx,
                force_index=len(videos) > 1,
            )
            video_container = self._policy.container_for_type("VideoObject")
            new_video = URIRef(f"{page_iri}/{video_container}/{video_slug}")
            self._swap_iri(graph, video, new_video)

    def _rewrite_images(self, graph: Graph, page_iri: URIRef) -> None:
        images: set[URIRef] = set()
        for obj in graph.objects(page_iri, URIRef(f"{SCHEMA}image")):
            if isinstance(obj, URIRef) and (
                self._is_typed_as(graph, obj, "ImageObject")
                or self._is_local_dependent_node(obj, page_iri)
            ):
                images.add(obj)
        for subject in graph.subjects(RDF.type, URIRef(f"{SCHEMA}ImageObject")):
            if str(subject).startswith(str(page_iri)):
                images.add(subject)

        for idx, image in enumerate(sorted(images, key=str), start=1):
            image_slug = self._entity_slug(
                graph,
                image,
                default_base="image-object",
                url_value=self._first_value(graph, image, "contentUrl"),
                index=idx,
                force_index=len(images) > 1,
            )
            image_container = self._policy.container_for_type("ImageObject")
            new_image = URIRef(f"{page_iri}/{image_container}/{image_slug}")
            self._swap_iri(graph, image, new_image)

    def _rewrite_howto(self, graph: Graph, page_iri: URIRef) -> None:
        howtos: set[URIRef] = set()
        for obj in graph.objects(page_iri, URIRef(f"{SCHEMA}mainEntity")):
            if isinstance(obj, URIRef) and self._is_typed_as(graph, obj, "HowTo"):
                howtos.add(obj)
        for obj in graph.objects(page_iri, URIRef(f"{SCHEMA}mentions")):
            if isinstance(obj, URIRef) and self._is_typed_as(graph, obj, "HowTo"):
                howtos.add(obj)
        for subject in graph.subjects(RDF.type, URIRef(f"{SCHEMA}HowTo")):
            if str(subject).startswith(str(page_iri)):
                howtos.add(subject)

        for idx, howto in enumerate(sorted(howtos, key=str), start=1):
            suffix = "" if len(howtos) == 1 else f"-{idx}"
            howto_container = self._policy.container_for_type("HowTo")
            new_howto = URIRef(f"{page_iri}/{howto_container}/how-to{suffix}")
            self._swap_iri(graph, howto, new_howto)

            steps = set(graph.objects(new_howto, URIRef(f"{SCHEMA}step")))
            ordered_steps = sorted(steps, key=self._step_sort_key)
            for step_idx, step in enumerate(ordered_steps, start=1):
                step_container = self._policy.container_for_type("HowToStep")
                new_step = URIRef(
                    f"{new_howto}/{step_container}/how-to-step-{step_idx}"
                )
                self._swap_iri(graph, step, new_step)

    def _rewrite_entity_roots(self, graph: Graph, dataset_uri: str) -> None:
        products = {
            subject
            for subject in graph.subjects()
            if self._has_entity_root_type(graph, subject)
        }
        seen: defaultdict[str, int] = defaultdict(int)
        for product in sorted(products, key=str):
            gtin = self._first_value(graph, product, "gtin")
            if gtin:
                product_iri = URIRef(f"{dataset_uri}/01/{normalize_slug(gtin)}")
            else:
                product_url = self._first_value(graph, product, "url")
                subject_type = self._preferred_type_name(graph, product)
                product_slug = self._entity_slug(
                    graph,
                    product,
                    default_base=subject_type,
                    url_value=product_url,
                )
                seen[product_slug] += 1
                if not product_url and seen[product_slug] > 1:
                    product_slug = f"{product_slug}-{seen[product_slug]}"

                normalized_type = self._policy.normalize_type_name(subject_type)
                container = self._policy.container_for_type(normalized_type)
                product_iri = URIRef(f"{dataset_uri}/{container}/{product_slug}")

            self._swap_iri(graph, product, product_iri)

            offers = sorted(
                {
                    offer
                    for offer in graph.objects(product_iri, URIRef(f"{SCHEMA}offers"))
                    if isinstance(offer, URIRef)
                },
                key=str,
            )
            for offer_idx, offer in enumerate(offers, start=1):
                offer_container = self._policy.container_for_type("Offer")
                new_offer = URIRef(f"{product_iri}/{offer_container}/offer-{offer_idx}")
                self._swap_iri(graph, offer, new_offer)
                graph.remove((product_iri, URIRef(f"{SCHEMA}offers"), offer))
                graph.add((product_iri, URIRef(f"{SCHEMA}offers"), new_offer))

                price_specs = sorted(
                    {
                        price_spec
                        for price_spec in graph.objects(
                            new_offer, URIRef(f"{SCHEMA}priceSpecification")
                        )
                        if isinstance(price_spec, URIRef)
                    },
                    key=str,
                )
                for price_idx, price_spec in enumerate(price_specs, start=1):
                    ps_container = self._policy.container_for_type("PriceSpecification")
                    new_price_spec = URIRef(
                        f"{new_offer}/{ps_container}/price-specification-{price_idx}"
                    )
                    self._swap_iri(graph, price_spec, new_price_spec)
                    graph.remove(
                        (
                            new_offer,
                            URIRef(f"{SCHEMA}priceSpecification"),
                            price_spec,
                        )
                    )
                    graph.add(
                        (
                            new_offer,
                            URIRef(f"{SCHEMA}priceSpecification"),
                            new_price_spec,
                        )
                    )

    def _entity_slug(
        self,
        graph: Graph,
        subject: URIRef,
        *,
        default_base: str,
        url_value: str | None,
        index: int | None = None,
        force_index: bool = False,
    ) -> str:
        base = self._base_from_priority(graph, subject) or default_base
        slug = normalize_slug(base) or "thing"
        if url_value:
            return f"{slug}-{self._url_hash(url_value)}"
        if force_index and index is not None:
            return f"{slug}-{index}"
        return slug

    def _base_from_priority(self, graph: Graph, subject: URIRef) -> str | None:
        predicates = ("name", "headline", "title", "gtin", "sku", "value")
        for pred in predicates:
            value = graph.value(subject, URIRef(f"{SCHEMA}{pred}"))
            if isinstance(value, (Literal, URIRef)):
                text = str(value).strip()
                if text:
                    return text
        return self._type_name_or_thing(graph, subject)

    @staticmethod
    def _type_name_or_thing(graph: Graph, subject: URIRef) -> str:
        types = CanonicalIdGenerator._schema_type_names(graph, subject)
        return sorted(types)[0] if types else "Thing"

    def _preferred_type_name(self, graph: Graph, subject: URIRef) -> str:
        types = self._schema_type_names(graph, subject)
        if not types:
            return "Thing"
        return self._policy.preferred_type(types)

    @staticmethod
    def _schema_type_names(graph: Graph, subject: URIRef) -> set[str]:
        values: set[str] = set()
        for obj in graph.objects(subject, RDF.type):
            if isinstance(obj, URIRef) and str(obj).startswith(SCHEMA):
                values.add(str(obj).split("/")[-1])
        return values

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
    def _first_value(
        graph: Graph, subject: URIRef, *predicate_suffixes: str
    ) -> str | None:
        for suffix in predicate_suffixes:
            value = graph.value(subject, URIRef(f"{SCHEMA}{suffix}"))
            if isinstance(value, (Literal, URIRef)):
                text = str(value).strip()
                if text:
                    return text
        return None

    @staticmethod
    def _swap_iri(graph: Graph, old_iri: URIRef, new_iri: URIRef) -> None:
        if old_iri == new_iri:
            return
        for subject, predicate, obj in list(graph.triples((old_iri, None, None))):
            graph.remove((subject, predicate, obj))
            graph.add((new_iri, predicate, obj))
        for subject, predicate, obj in list(graph.triples((None, None, old_iri))):
            if predicate == URIRef(f"{SCHEMA}url"):
                continue
            graph.remove((subject, predicate, obj))
            graph.add((subject, predicate, new_iri))

    @staticmethod
    def _step_sort_key(step: URIRef) -> tuple[int, str]:
        match = re.search(r"(\d+)(?!.*\d)", str(step))
        if match:
            return int(match.group(1)), str(step)
        return 0, str(step)

    def _has_page_root_type(self, graph: Graph, subject: URIRef) -> bool:
        types = self._schema_type_names(graph, subject)
        return any(self._policy.is_page_root_type(value) for value in types)

    def _has_entity_root_type(self, graph: Graph, subject: URIRef) -> bool:
        types = self._schema_type_names(graph, subject)
        return any(self._policy.is_entity_root_type(value) for value in types)

    @staticmethod
    def _is_typed_as(graph: Graph, subject: URIRef, type_name: str) -> bool:
        return (subject, RDF.type, URIRef(f"{SCHEMA}{type_name}")) in graph

    @staticmethod
    def _is_local_dependent_node(subject: URIRef, parent: URIRef) -> bool:
        return str(subject).startswith(str(parent))

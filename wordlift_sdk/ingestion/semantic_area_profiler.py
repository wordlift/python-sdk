from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from wordlift_sdk.kg_build.id_generator import normalize_slug
from wordlift_sdk.kg_build.id_policy import DEFAULT_ID_POLICY, IdPolicy
from wordlift_sdk.structured_data.constants import DEFAULT_BASE_URL
from wordlift_sdk.structured_data.structured_data_engine import StructuredDataEngine

from .api import resolve_ingestion_source_items
from .factory import create_orchestrator
from .models import LoadedPage, SourceItem
from .resolver import ResolvedIngestionConfig


_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_DEFAULT_SAMPLE_SIZE = 12
_MIN_COHERENT_SHARE = 0.67
_MAX_MIXED_SHARE = 0.5
_MIN_RECURRING_TYPE_COUNT = 2
_RELEVANT_SECONDARY_TYPES = {
    "AggregateOffer",
    "AggregateRating",
    "Answer",
    "BreadcrumbList",
    "ImageObject",
    "ListItem",
    "Offer",
    "PriceSpecification",
    "Question",
    "Rating",
    "Review",
    "VideoObject",
}
_PAGE_TYPE_PRIORITIES = (
    "Article",
    "BlogPosting",
    "NewsArticle",
    "TechArticle",
    "AnalysisNewsArticle",
    "OpinionNewsArticle",
    "ReviewNewsArticle",
    "LiveBlogPosting",
    "Product",
    "Service",
    "SoftwareApplication",
    "Event",
    "Recipe",
    "HowTo",
    "FAQPage",
    "QAPage",
    "Course",
    "Person",
    "Organization",
    "LocalBusiness",
    "Brand",
    "VideoObject",
    "ImageObject",
    "Book",
    "Movie",
    "Dataset",
    "DiscussionForumPosting",
    "Review",
    "CreativeWork",
    "WebSite",
    "WebPage",
)
_PAGE_TYPE_SET = set(_PAGE_TYPE_PRIORITIES)
_MAIN_ENTITY_HEURISTIC_TYPES = {
    "Article",
    "BlogPosting",
    "NewsArticle",
    "TechArticle",
    "AnalysisNewsArticle",
    "OpinionNewsArticle",
    "ReviewNewsArticle",
    "LiveBlogPosting",
    "Product",
    "Service",
    "SoftwareApplication",
    "Event",
    "Recipe",
    "HowTo",
    "FAQPage",
    "QAPage",
    "Course",
    "Person",
    "Organization",
    "LocalBusiness",
    "Brand",
    "VideoObject",
    "ImageObject",
    "Book",
    "Movie",
    "Dataset",
    "DiscussionForumPosting",
    "Review",
    "CreativeWork",
    "WebSite",
    "WebPage",
}
_SUPPORT_ONLY_TYPES = {
    "AggregateOffer",
    "AggregateRating",
    "Answer",
    "BreadcrumbList",
    "ListItem",
    "Offer",
    "PriceSpecification",
    "Question",
    "Rating",
    "HowToStep",
}
_SUPPORTED_INSPECTION_LOADERS = {
    "simple",
    "playwright",
    "web_scrape_api",
    "proxy",
    "premium_scraper",
}


class SemanticAreaProfilerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SemanticAreaProfileRequest:
    sitemap: str
    website_url: str
    url_regex: str | None = None
    sample_size: int = _DEFAULT_SAMPLE_SIZE
    sampling_strategy: str = "round_robin_bucket"
    sampling_seed: str | int | None = None
    inspect_loader: str = "simple"
    inspect_timeout_ms: int = 30_000
    inspect_retry_attempts: int = 1
    inspect_retry_backoff_ms: int = 0
    main_entity_min_confidence: float = 0.6
    strict_mode: bool = False
    dataset_uri: str | None = None
    api_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    ssl_ca_cert: str | None = None


@dataclass(frozen=True)
class SampledWebPage:
    url: str
    canonical: str | None
    title: str | None


@dataclass(frozen=True)
class SemanticAreaProfileResult:
    scope: dict[str, Any]
    main_entity: str
    additional_entity_types: list[str]
    explanation: str
    explanation_metadata: dict[str, Any]
    sampled_web_pages: list[SampledWebPage]
    sample_semantic_data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "main_entity": self.main_entity,
            "additional_entity_types": list(self.additional_entity_types),
            "explanation": self.explanation,
            "explanation_metadata": self.explanation_metadata,
            "sampled_web_pages": [asdict(page) for page in self.sampled_web_pages],
            "sample_semantic_data": self.sample_semantic_data,
        }


class DatasetUriResolver(Protocol):
    def resolve(self, request: SemanticAreaProfileRequest) -> str: ...


class RuntimeDatasetUriResolver:
    """Resolve a dataset URI from explicit input or runtime account context.

    The PoC keeps this interface intentionally small so the host can inject
    whatever runtime object it has without forcing a new SDK dependency.
    """

    def resolve(self, request: SemanticAreaProfileRequest) -> str:
        if request.dataset_uri:
            dataset_uri = request.dataset_uri.strip().rstrip("/")
            if dataset_uri:
                return dataset_uri

        if not request.api_key:
            raise SemanticAreaProfilerError(
                "dataset_uri is required unless api_key is provided so it can be "
                "resolved from runtime context."
            )

        return (
            StructuredDataEngine()
            .get_dataset_uri(
                api_key=request.api_key,
                base_url=request.base_url or DEFAULT_BASE_URL,
                ssl_ca_cert=request.ssl_ca_cert,
            )
            .rstrip("/")
        )


class SemanticDataSerializer(Protocol):
    def serialize(self, nodes: list[dict[str, Any]]) -> dict[str, Any]: ...


class JsonLdSemanticDataSerializer:
    def serialize(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return {"@context": "https://schema.org", "@graph": nodes}


@dataclass(frozen=True)
class _RawNode:
    raw_id: str
    page_url: str
    order: int
    parent_raw_id: str | None
    source_property: str | None
    types: tuple[str, ...]
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _PageInspection:
    page: LoadedPage
    title: str | None
    canonical: str | None
    jsonld_nodes: list[dict[str, Any]]
    page_vote: str
    page_vote_source: str
    page_vote_score: int
    type_evidence: list[str]


class SemanticAreaProfiler:
    def __init__(
        self,
        *,
        source_discovery: Callable[
            [Mapping[str, Any]], Any
        ] = resolve_ingestion_source_items,
        orchestrator_factory: Callable[..., Any] = create_orchestrator,
        dataset_uri_resolver: DatasetUriResolver | None = None,
        serializer: SemanticDataSerializer | None = None,
        policy: IdPolicy = DEFAULT_ID_POLICY,
    ) -> None:
        self._source_discovery = source_discovery
        self._orchestrator_factory = orchestrator_factory
        self._dataset_uri_resolver = dataset_uri_resolver or RuntimeDatasetUriResolver()
        self._serializer = serializer or JsonLdSemanticDataSerializer()
        self._policy = policy

    def profile(self, request: SemanticAreaProfileRequest) -> SemanticAreaProfileResult:
        if request.sample_size < 1:
            raise SemanticAreaProfilerError("sample_size must be >= 1")
        if not (0.0 <= request.main_entity_min_confidence <= 1.0):
            raise SemanticAreaProfilerError(
                "main_entity_min_confidence must be between 0.0 and 1.0"
            )

        dataset_uri = self._dataset_uri_resolver.resolve(request).rstrip("/")
        discovered_urls = self._discover_sitemap_urls(request)
        filtered_urls = self._filter_urls(request, discovered_urls)
        matched_url_count = len(filtered_urls)
        sampled_urls = self._sample_urls(request, filtered_urls)
        sampled_pages = self._inspect_pages(request, sampled_urls)
        page_inspections = [self._inspect_page(page) for page in sampled_pages]
        main_entity, coherence, evidence, main_confidence = self._infer_main_entity(
            page_inspections, min_confidence=request.main_entity_min_confidence
        )
        additional_entity_types, support_evidence = self._infer_additional_types(
            page_inspections, main_entity
        )
        sample_nodes = self._build_sample_semantic_data(
            dataset_uri=dataset_uri,
            page_inspections=page_inspections,
            main_entity=main_entity,
        )
        sample_semantic_data = self._serializer.serialize(sample_nodes)
        self._validate_serialized_output(
            dataset_uri=dataset_uri,
            serialized=sample_semantic_data,
            strict_mode=request.strict_mode,
        )

        scope = {
            "sitemap": str(request.sitemap),
            "website_url": request.website_url,
            "matched_url_count": matched_url_count,
            "sample_size": request.sample_size,
            "sampled_url_count": len(page_inspections),
            "sampling_strategy": request.sampling_strategy,
            "sampling_seed": str(request.sampling_seed)
            if request.sampling_seed is not None
            else None,
            "inspect_loader": request.inspect_loader,
        }
        if request.url_regex is not None:
            scope["url_regex"] = request.url_regex

        explanation_metadata = self._build_explanation_metadata(
            page_inspections=page_inspections,
            main_entity=main_entity,
            additional_entity_types=additional_entity_types,
            coherence=coherence,
            evidence=evidence,
            support_evidence=support_evidence,
            main_confidence=main_confidence,
        )
        explanation = self._render_explanation(explanation_metadata)

        return SemanticAreaProfileResult(
            scope=scope,
            main_entity=main_entity,
            additional_entity_types=additional_entity_types,
            explanation=explanation,
            explanation_metadata=explanation_metadata,
            sampled_web_pages=[
                SampledWebPage(
                    url=page.page.final_url or page.page.url,
                    canonical=page.canonical,
                    title=page.title,
                )
                for page in page_inspections
            ],
            sample_semantic_data=sample_semantic_data,
        )

    def _discover_sitemap_urls(self, request: SemanticAreaProfileRequest) -> list[str]:
        sitemap = str(request.sitemap)
        if self._looks_like_local_file(sitemap):
            return self._discover_urls_from_file(Path(sitemap))

        source_bundle = {
            "INGEST_SOURCE": "sitemap",
            "INGEST_LOADER": "simple",
            "SITEMAP_URL": sitemap,
        }
        result = self._source_discovery(source_bundle)
        items = getattr(result, "items", result)
        return [str(item.url).strip() for item in items if str(item.url).strip()]

    def _filter_urls(
        self, request: SemanticAreaProfileRequest, urls: list[str]
    ) -> list[str]:
        boundary = self._normalize_boundary(request.website_url)
        filtered = [url for url in urls if self._is_within_boundary(url, boundary)]
        if request.url_regex:
            pattern = re.compile(request.url_regex)
            filtered = [url for url in filtered if pattern.search(url)]
        return self._deduplicate_and_sort(filtered)

    def _sample_urls(
        self, request: SemanticAreaProfileRequest, urls: list[str]
    ) -> list[str]:
        sample_size = request.sample_size
        if len(urls) <= sample_size:
            return list(urls)

        strategy = (request.sampling_strategy or "round_robin_bucket").strip().lower()
        if strategy == "hash_stride":
            seed = str(
                request.sampling_seed if request.sampling_seed is not None else ""
            )
            ranked = sorted(
                urls,
                key=lambda url: (
                    _sha256_hex(f"{seed}|{self._normalize_url(url)}"),
                    self._normalize_url_for_sort(url),
                ),
            )
            return ranked[:sample_size]
        if strategy != "round_robin_bucket":
            raise SemanticAreaProfilerError(
                "sampling_strategy must be one of: round_robin_bucket, hash_stride"
            )

        buckets: dict[str, list[str]] = defaultdict(list)
        for url in urls:
            buckets[self._sample_bucket(url, request.website_url)].append(url)

        for bucket_urls in buckets.values():
            bucket_urls.sort(key=self._normalize_url_for_sort)

        ordered_bucket_keys = sorted(buckets)
        sampled: list[str] = []
        positions = {bucket: 0 for bucket in ordered_bucket_keys}

        # Diversification strategy:
        # take one URL per path bucket in round-robin order so sibling sections
        # do not dominate the sample. The ordering is deterministic because both
        # buckets and their members are sorted first.
        while len(sampled) < sample_size:
            progressed = False
            for bucket in ordered_bucket_keys:
                index = positions[bucket]
                bucket_urls = buckets[bucket]
                if index >= len(bucket_urls):
                    continue
                sampled.append(bucket_urls[index])
                positions[bucket] = index + 1
                progressed = True
                if len(sampled) >= sample_size:
                    break
            if not progressed:
                break

        return sampled

    def _inspect_pages(
        self, request: SemanticAreaProfileRequest, sampled_urls: list[str]
    ) -> list[LoadedPage]:
        if not sampled_urls:
            return []
        loader_name = (request.inspect_loader or "simple").strip()
        if loader_name not in _SUPPORTED_INSPECTION_LOADERS:
            allowed = ", ".join(sorted(_SUPPORTED_INSPECTION_LOADERS))
            raise SemanticAreaProfilerError(
                f"Unsupported inspect_loader {loader_name!r}. Allowed: {allowed}"
            )

        items = [
            SourceItem(id=f"semantic-area:{index}", url=url)
            for index, url in enumerate(sampled_urls, start=1)
        ]
        config = ResolvedIngestionConfig(
            source_name="urls",
            loader_name=loader_name,
            passthrough_when_html=False,
            timeout_ms=request.inspect_timeout_ms,
            retry_attempts=request.inspect_retry_attempts,
            retry_backoff_ms=request.inspect_retry_backoff_ms,
            source_config={"urls": sampled_urls},
            loader_config={},
            url_regex=None,
            warnings=tuple(),
        )
        orchestrator = self._orchestrator_factory()
        result = orchestrator.run_with_items(config, items)
        return list(result.pages)

    def _inspect_page(self, page: LoadedPage) -> _PageInspection:
        parser = _PageHtmlParser()
        parser.feed(page.html)
        jsonld_nodes = _extract_jsonld_nodes(page.html)
        type_votes = self._page_type_votes(jsonld_nodes, parser.meta, parser.title)
        page_vote, page_vote_source, page_vote_score, evidence = self._choose_page_vote(
            type_votes,
            parser.meta,
            parser.title,
            page.html,
        )
        canonical = parser.canonical or (
            page.final_url if page.final_url and page.final_url != page.url else None
        )
        return _PageInspection(
            page=page,
            title=parser.title,
            canonical=canonical,
            jsonld_nodes=jsonld_nodes,
            page_vote=page_vote,
            page_vote_source=page_vote_source,
            page_vote_score=page_vote_score,
            type_evidence=evidence,
        )

    def _page_type_votes(
        self,
        nodes: list[dict[str, Any]],
        meta: dict[str, list[str]],
        title: str | None,
    ) -> dict[str, int]:
        votes: dict[str, int] = {}
        for node in nodes:
            node_types = _node_types(node)
            node_score = self._node_specificity_score(node, meta, title)
            for type_name in node_types:
                if type_name not in _MAIN_ENTITY_HEURISTIC_TYPES:
                    continue
                current = votes.get(type_name, 0)
                if node_score > current:
                    votes[type_name] = node_score
        return votes

    def _choose_page_vote(
        self,
        type_votes: dict[str, int],
        meta: dict[str, list[str]],
        title: str | None,
        html: str,
    ) -> tuple[str, str, int, list[str]]:
        evidence: list[str] = []
        if type_votes:
            sorted_votes = sorted(
                type_votes.items(),
                key=lambda item: (-item[1], self._type_priority(item[0]), item[0]),
            )
            vote, score = sorted_votes[0]
            evidence = [f"{type_name}={value}" for type_name, value in sorted_votes[:4]]
            if score >= 3:
                return vote, "explicit_jsonld", score, evidence

        fallback_vote, fallback_score, fallback_evidence = self._heuristic_page_vote(
            meta, title, html
        )
        if fallback_score >= 2:
            return fallback_vote, "html_heuristic", fallback_score, fallback_evidence

        return "WebPage", "fallback", 1, evidence or fallback_evidence

    def _heuristic_page_vote(
        self,
        meta: dict[str, list[str]],
        title: str | None,
        html: str,
    ) -> tuple[str, int, list[str]]:
        lowered_html = html.lower()
        evidence: list[str] = []
        if any(key in meta for key in ("article:published_time", "article:author")):
            evidence.append("article_meta")
            return "Article", 3, evidence
        og_types = {
            value.lower()
            for key in ("og:type", "twitter:card")
            for value in meta.get(key, [])
        }
        if og_types:
            if {"article", "article:blog", "blog", "news"} & og_types:
                evidence.append("og_article")
                return "Article", 3, evidence
            if "product" in og_types:
                evidence.append("og_product")
                return "Product", 3, evidence
            if "event" in og_types:
                evidence.append("og_event")
                return "Event", 3, evidence
        if "<article" in lowered_html or 'itemprop="articlebody"' in lowered_html:
            evidence.append("article_tag")
            return "Article", 2, evidence
        if (
            re.search(r"\b(?:\$|€|£)\s?\d", lowered_html)
            or "add to cart" in lowered_html
        ):
            evidence.append("product_signal")
            return "Product", 2, evidence
        if "<time" in lowered_html and title:
            evidence.append("time_and_title")
            return "Article", 2, evidence
        return "WebPage", 1, evidence

    def _node_specificity_score(
        self,
        node: dict[str, Any],
        meta: dict[str, list[str]],
        title: str | None,
    ) -> int:
        types = _node_types(node)
        if not types:
            return 0

        score = 0
        for type_name in types:
            score = max(score, 20 - self._type_priority(type_name))

        fields = {key for key in node.keys() if not key.startswith("@")}
        has = fields.__contains__
        if "Article" in types or "BlogPosting" in types or "NewsArticle" in types:
            if has("headline") or has("articleBody") or has("datePublished"):
                score += 4
            if has("author") or has("publisher"):
                score += 2
        if "Product" in types or "Service" in types:
            if has("offers") or has("sku") or has("gtin") or has("brand"):
                score += 4
        if "Person" in types:
            if has("givenName") or has("familyName") or has("jobTitle"):
                score += 4
        if "Event" in types:
            if has("startDate") or has("location"):
                score += 4
        if "FAQPage" in types or "QAPage" in types:
            if has("mainEntity"):
                score += 4
        if "HowTo" in types:
            if has("step"):
                score += 4
        if "Recipe" in types:
            if has("recipeIngredient") or has("recipeInstructions"):
                score += 4
        if "VideoObject" in types or "ImageObject" in types:
            if has("contentUrl") or has("embedUrl"):
                score += 3
        if "Organization" in types or "Brand" in types or "WebSite" in types:
            if has("logo") or has("address") or has("contactPoint") or has("name"):
                score += 2
        if "WebPage" in types:
            if title:
                score += 1
            if meta.get("description"):
                score += 1
        return score

    def _infer_main_entity(
        self,
        page_inspections: list[_PageInspection],
        *,
        min_confidence: float,
    ) -> tuple[str, str, list[str], float]:
        specific_votes = [
            page.page_vote for page in page_inspections if page.page_vote != "WebPage"
        ]
        if not specific_votes:
            return "WebPage", "ambiguous", ["no specific page vote"], 0.0

        counts = Counter(specific_votes)
        best_type, best_count = counts.most_common(1)[0]
        runner_up_count = counts.most_common(2)[1][1] if len(counts) > 1 else 0
        total = len(page_inspections)
        evidence = [
            f"{type_name}={count}"
            for type_name, count in sorted(
                counts.items(),
                key=lambda item: (-item[1], self._type_priority(item[0]), item[0]),
            )
        ]

        reliability_threshold = 1 if total == 1 else max(2, (total + 1) // 2)
        confidence = best_count / max(total, 1)
        reliable = (
            best_count >= reliability_threshold
            and best_count > runner_up_count
            and confidence >= min_confidence
        )
        coherence = self._coherence_label(best_count, runner_up_count, total)
        if reliable:
            return best_type, coherence, evidence, confidence

        return "WebPage", coherence, evidence, confidence

    def _infer_additional_types(
        self, page_inspections: list[_PageInspection], main_entity: str
    ) -> tuple[list[str], list[str]]:
        counts: Counter[str] = Counter()
        support_pages: dict[str, set[str]] = defaultdict(set)
        for page in page_inspections:
            seen_in_page: set[str] = set()
            for node in page.jsonld_nodes:
                for type_name in _node_types(node):
                    if type_name == "Thing":
                        continue
                    if type_name == "WebPage":
                        continue
                    if type_name == main_entity:
                        continue
                    counts[type_name] += 1
                    if type_name not in seen_in_page:
                        support_pages[type_name].add(page.page.url)
                        seen_in_page.add(type_name)

        total = len(page_inspections)
        threshold = max(_MIN_RECURRING_TYPE_COUNT, (total + 1) // 3)
        selected: list[str] = []
        evidence: list[str] = []
        for type_name, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], self._type_priority(item[0]), item[0]),
        ):
            recurring_pages = len(support_pages[type_name])
            if (
                type_name not in _RELEVANT_SECONDARY_TYPES
                and recurring_pages < threshold
            ):
                continue
            if recurring_pages < threshold:
                continue
            selected.append(type_name)
            evidence.append(f"{type_name}={count} nodes on {recurring_pages} pages")
        return selected, evidence

    def _build_sample_semantic_data(
        self,
        *,
        dataset_uri: str,
        page_inspections: list[_PageInspection],
        main_entity: str,
    ) -> dict[str, Any]:
        nodes_by_iri: dict[str, dict[str, Any]] = {}
        raw_nodes_by_page: list[
            tuple[
                _PageInspection, list[_RawNode], dict[str, list[tuple[str, str | None]]]
            ]
        ] = []
        for page_index, inspection in enumerate(page_inspections, start=1):
            raw_nodes, incoming = self._raw_nodes_from_page(inspection, page_index)
            raw_nodes_by_page.append((inspection, raw_nodes, incoming))

        raw_id_to_final_id: dict[str, str] = {}
        for inspection, raw_nodes, incoming in raw_nodes_by_page:
            page_node = self._build_page_node(dataset_uri, inspection)
            raw_id_to_final_id[page_node["@id"]] = page_node["@id"]
            nodes_by_iri[page_node["@id"]] = page_node
            duplicate_indexes = self._duplicate_indexes(raw_nodes, incoming)
            for raw_node in raw_nodes:
                final_node = self._normalize_raw_node(
                    raw_node=raw_node,
                    dataset_uri=dataset_uri,
                    page_iri=page_node["@id"],
                    raw_nodes_by_id={node.raw_id: node for node in raw_nodes},
                    incoming=incoming,
                    memo=raw_id_to_final_id,
                    duplicate_indexes=duplicate_indexes,
                    normalized_nodes=nodes_by_iri,
                )
                if final_node is not None:
                    nodes_by_iri[final_node["@id"]] = final_node
            if main_entity != "WebPage":
                main_candidate = next(
                    (
                        node
                        for node in nodes_by_iri.values()
                        if node.get("mainEntityOfPage") == page_node["@id"]
                        and main_entity in _node_types(node)
                    ),
                    None,
                )
                if main_candidate is not None:
                    stored_page_node = nodes_by_iri.get(page_node["@id"], page_node)
                    stored_page_node["mainEntity"] = main_candidate["@id"]

        nodes = self._deduplicate_nodes(list(nodes_by_iri.values()))
        nodes.sort(key=lambda node: str(node.get("@id", "")))
        return nodes

    def _raw_nodes_from_page(
        self, inspection: _PageInspection, page_index: int
    ) -> tuple[list[_RawNode], dict[str, list[tuple[str, str | None]]]]:
        parser = _PageJsonLdParser()
        parser.feed(inspection.page.html)
        raw_nodes: dict[str, _RawNode] = {}
        incoming: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        order = 0

        def add_node(
            payload: dict[str, Any],
            *,
            parent_raw_id: str | None,
            source_property: str | None,
        ) -> str:
            nonlocal order
            order += 1
            raw_id = str(payload.get("@id") or f"_:page-{page_index}-{order}")
            properties: dict[str, Any] = {}
            for key, value in payload.items():
                if key in {"@id", "@type"}:
                    continue
                properties[key] = normalize_jsonld_value(
                    value,
                    page_index=page_index,
                    parent_raw_id=raw_id,
                    source_property=key,
                    add_node=add_node,
                    incoming=incoming,
                )
            raw_nodes[raw_id] = _RawNode(
                raw_id=raw_id,
                page_url=inspection.page.url,
                order=order,
                parent_raw_id=parent_raw_id,
                source_property=source_property,
                types=tuple(_node_types(payload)),
                properties=properties,
            )
            if parent_raw_id is not None:
                incoming[raw_id].append((parent_raw_id, source_property))
            return raw_id

        for block in parser.blocks:
            try:
                data = json.loads(block)
            except Exception:
                continue
            for item in _iter_jsonld_items(data):
                if isinstance(item, dict):
                    add_node(item, parent_raw_id=None, source_property=None)

        return list(raw_nodes.values()), incoming

    def _normalize_raw_node(
        self,
        *,
        raw_node: _RawNode,
        dataset_uri: str,
        page_iri: str,
        raw_nodes_by_id: dict[str, _RawNode],
        incoming: dict[str, list[tuple[str, str | None]]],
        memo: dict[str, str],
        duplicate_indexes: dict[str, int],
        normalized_nodes: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        if raw_node.raw_id in memo:
            return None

        node_type = self._preferred_type(raw_node)
        parent_iri = self._resolve_parent_iri(
            raw_node=raw_node,
            dataset_uri=dataset_uri,
            page_iri=page_iri,
            raw_nodes_by_id=raw_nodes_by_id,
            incoming=incoming,
            memo=memo,
            duplicate_indexes=duplicate_indexes,
            normalized_nodes=normalized_nodes,
        )
        iri = self._build_node_iri(
            dataset_uri=dataset_uri,
            node_type=node_type,
            raw_node=raw_node,
            parent_iri=parent_iri,
            duplicate_index=duplicate_indexes.get(raw_node.raw_id),
        )
        memo[raw_node.raw_id] = iri

        node = {"@id": iri, "@type": f"http://schema.org/{node_type}"}
        if node_type == "WebPage":
            node["url"] = self._page_url(raw_node)
            if raw_node.properties.get("name"):
                node["name"] = self._first_text(raw_node.properties.get("name"))
            normalized_nodes[iri] = node
            return node

        for key, value in raw_node.properties.items():
            if key == "url":
                node["url"] = self._stringify_value(value)
                continue
            if (
                key == "mainEntityOfPage"
                and isinstance(value, dict)
                and value.get("@id")
            ):
                raw_ref = str(value["@id"])
                node[key] = memo.get(
                    raw_ref, self._stable_reference_iri(dataset_uri, raw_ref)
                )
                continue
            node[key] = self._rewrite_value(
                value=value,
                dataset_uri=dataset_uri,
                raw_nodes_by_id=raw_nodes_by_id,
                incoming=incoming,
                memo=memo,
                page_iri=page_iri,
                duplicate_indexes=duplicate_indexes,
                normalized_nodes=normalized_nodes,
            )

        if "mainEntityOfPage" not in node and page_iri and node_type != "WebPage":
            node["mainEntityOfPage"] = page_iri
        normalized_nodes[iri] = node
        return node

    def _resolve_parent_iri(
        self,
        *,
        raw_node: _RawNode,
        dataset_uri: str,
        page_iri: str,
        raw_nodes_by_id: dict[str, _RawNode],
        incoming: dict[str, list[tuple[str, str | None]]],
        memo: dict[str, str],
        duplicate_indexes: dict[str, int],
        normalized_nodes: dict[str, dict[str, Any]],
    ) -> str:
        node_type = self._preferred_type(raw_node)
        rule = self._policy.dependency_rule_for(node_type)
        if rule is None:
            return dataset_uri

        if raw_node.parent_raw_id and raw_node.parent_raw_id in memo:
            return memo[raw_node.parent_raw_id]
        if raw_node.parent_raw_id and raw_node.parent_raw_id in raw_nodes_by_id:
            parent_iri = self._normalize_parent_reference(
                parent_raw_id=raw_node.parent_raw_id,
                dataset_uri=dataset_uri,
                page_iri=page_iri,
                raw_nodes_by_id=raw_nodes_by_id,
                incoming=incoming,
                memo=memo,
                duplicate_indexes=duplicate_indexes,
                normalized_nodes=normalized_nodes,
            )
            if parent_iri:
                return parent_iri

        for source_raw_id, source_property in incoming.get(raw_node.raw_id, []):
            if source_property not in rule.parent_predicates:
                continue
            if source_raw_id in memo:
                return memo[source_raw_id]
            if source_raw_id in raw_nodes_by_id:
                parent = raw_nodes_by_id[source_raw_id]
                if node_type == "FAQPage" and self._preferred_type(parent) == "WebPage":
                    return self._normalize_parent_reference(
                        parent_raw_id=source_raw_id,
                        dataset_uri=dataset_uri,
                        page_iri=page_iri,
                        raw_nodes_by_id=raw_nodes_by_id,
                        incoming=incoming,
                        memo=memo,
                        duplicate_indexes=duplicate_indexes,
                        normalized_nodes=normalized_nodes,
                    )
                if self._preferred_type(parent) == rule.parent_type:
                    return self._normalize_parent_reference(
                        parent_raw_id=source_raw_id,
                        dataset_uri=dataset_uri,
                        page_iri=page_iri,
                        raw_nodes_by_id=raw_nodes_by_id,
                        incoming=incoming,
                        memo=memo,
                        duplicate_indexes=duplicate_indexes,
                        normalized_nodes=normalized_nodes,
                    )

        if rule.parent_type == "WebPage":
            return page_iri

        return dataset_uri

    def _normalize_parent_reference(
        self,
        *,
        parent_raw_id: str,
        dataset_uri: str,
        page_iri: str,
        raw_nodes_by_id: dict[str, _RawNode],
        incoming: dict[str, list[tuple[str, str | None]]],
        memo: dict[str, str],
        duplicate_indexes: dict[str, int],
        normalized_nodes: dict[str, dict[str, Any]],
    ) -> str:
        if parent_raw_id in memo:
            return memo[parent_raw_id]
        parent = raw_nodes_by_id[parent_raw_id]
        parent_node = self._normalize_raw_node(
            raw_node=parent,
            dataset_uri=dataset_uri,
            page_iri=page_iri,
            raw_nodes_by_id=raw_nodes_by_id,
            incoming=incoming,
            memo=memo,
            duplicate_indexes=duplicate_indexes,
            normalized_nodes=normalized_nodes,
        )
        return parent_node["@id"] if parent_node is not None else memo[parent_raw_id]

    def _build_node_iri(
        self,
        *,
        dataset_uri: str,
        node_type: str,
        raw_node: _RawNode,
        parent_iri: str,
        duplicate_index: int | None,
    ) -> str:
        gtin = self._first_text(raw_node.properties.get("gtin"))
        if gtin:
            return f"{dataset_uri}/01/{normalize_slug(gtin)}"

        base = self._slug_source(raw_node, node_type)
        slug = normalize_slug(base) or "thing"
        url_value = self._first_text(raw_node.properties.get("url"))
        if url_value:
            slug = f"{slug}-{self._normalize_url_for_hash(url_value)}"
        elif duplicate_index is not None:
            slug = f"{slug}-{duplicate_index}"

        container = self._policy.container_for_type(node_type)
        prefix = parent_iri.rstrip("/")
        if prefix == dataset_uri.rstrip("/"):
            return f"{dataset_uri}/{container}/{slug}"
        return f"{prefix}/{container}/{slug}"

    def _rewrite_value(
        self,
        *,
        value: Any,
        dataset_uri: str,
        raw_nodes_by_id: dict[str, _RawNode],
        incoming: dict[str, list[tuple[str, str | None]]],
        memo: dict[str, str],
        page_iri: str,
        duplicate_indexes: dict[str, int],
        normalized_nodes: dict[str, dict[str, Any]],
    ) -> Any:
        if isinstance(value, dict):
            ref = value.get("@id")
            if ref is not None:
                ref_text = str(ref)
                if ref_text in memo:
                    return memo[ref_text]
                if ref_text in raw_nodes_by_id:
                    nested = self._normalize_raw_node(
                        raw_node=raw_nodes_by_id[ref_text],
                        dataset_uri=dataset_uri,
                        page_iri=page_iri,
                        raw_nodes_by_id=raw_nodes_by_id,
                        incoming=incoming,
                        memo=memo,
                        duplicate_indexes=duplicate_indexes,
                        normalized_nodes=normalized_nodes,
                    )
                    if nested is not None:
                        return nested["@id"]
                return self._stable_reference_iri(dataset_uri, ref_text)
            if "@value" in value:
                return value["@value"]
            # Flat serialization contract: avoid inline anonymous objects.
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        if isinstance(value, list):
            return [
                self._rewrite_value(
                    value=item,
                    dataset_uri=dataset_uri,
                    raw_nodes_by_id=raw_nodes_by_id,
                    incoming=incoming,
                    memo=memo,
                    page_iri=page_iri,
                    duplicate_indexes=duplicate_indexes,
                    normalized_nodes=normalized_nodes,
                )
                for item in value
            ]
        return value

    def _build_page_node(
        self,
        dataset_uri: str,
        inspection: _PageInspection,
    ) -> dict[str, Any]:
        title = inspection.title or self._first_page_title_hint(inspection.page.html)
        page_url = inspection.page.final_url or inspection.page.url
        slug_source = title or "web-page"
        slug = normalize_slug(slug_source) or "web-page"
        slug = f"{slug}-{self._normalize_url_for_hash(page_url)}"
        iri = f"{dataset_uri}/{self._policy.container_for_type('WebPage')}/{slug}"
        node = {
            "@id": iri,
            "@type": "http://schema.org/WebPage",
            "url": page_url,
        }
        if title:
            node["name"] = title
        return node

    def _build_explanation_metadata(
        self,
        *,
        page_inspections: list[_PageInspection],
        main_entity: str,
        additional_entity_types: list[str],
        coherence: str,
        evidence: list[str],
        support_evidence: list[str],
        main_confidence: float,
    ) -> dict[str, Any]:
        if not page_inspections:
            return {
                "main_entity_reason": "no sampled pages were successfully inspected",
                "main_confidence": 0.0,
                "additional_entity_reasons": [],
                "page_type_evidence": ["none"],
                "support_evidence": ["none"],
                "sample_pages": [],
                "coherence": "ambiguous",
                "notable_exclusions": [
                    "insufficient evidence to promote specific types"
                ],
                "vote_counts": {},
            }

        page_summaries = []
        for page in page_inspections[:5]:
            page_summaries.append(
                f"{page.page.final_url or page.page.url} -> {page.page_vote} "
                f"({page.page_vote_source}, score={page.page_vote_score})"
            )

        all_votes = Counter(page.page_vote for page in page_inspections)
        specific_votes = {
            type_name: count
            for type_name, count in all_votes.items()
            if type_name != "WebPage"
        }
        main_reason = (
            f"page votes were {dict(sorted(specific_votes.items()))}"
            if main_entity != "WebPage"
            else "no specific type met reliability threshold"
        )
        return {
            "main_entity_reason": main_reason,
            "main_confidence": round(main_confidence, 4),
            "additional_entity_reasons": list(support_evidence),
            "page_type_evidence": list(evidence) if evidence else ["none"],
            "support_evidence": list(support_evidence)
            if support_evidence
            else ["none"],
            "sample_pages": page_summaries,
            "coherence": coherence,
            "notable_exclusions": [
                "WebPage omitted from additional types when a specific main_entity is reliable",
                "weak or contradictory candidates are not promoted",
            ],
            "vote_counts": dict(sorted(specific_votes.items())),
            "additional_entity_types": list(additional_entity_types),
        }

    def _render_explanation(self, metadata: dict[str, Any]) -> str:
        return (
            f"main_entity_reason={metadata.get('main_entity_reason')}. "
            f"main_confidence={metadata.get('main_confidence')}. "
            f"additional_entity_types={metadata.get('additional_entity_types', [])}. "
            f"page_type_evidence={metadata.get('page_type_evidence', [])}. "
            f"support_evidence={metadata.get('support_evidence', [])}. "
            f"sample_pages={metadata.get('sample_pages', [])}. "
            f"coherence={metadata.get('coherence')}. "
            f"notable_exclusions={metadata.get('notable_exclusions', [])}"
        )

    def _validate_serialized_output(
        self,
        *,
        dataset_uri: str,
        serialized: dict[str, Any],
        strict_mode: bool,
    ) -> None:
        nodes = serialized.get("@graph")
        if not isinstance(nodes, list):
            raise SemanticAreaProfilerError(
                "sample_semantic_data must be a JSON-LD graph with @graph list."
            )

        iri_to_node: dict[str, dict[str, Any]] = {}
        for node in nodes:
            if not isinstance(node, dict):
                raise SemanticAreaProfilerError("Each semantic node must be an object.")
            iri = str(node.get("@id") or "")
            if not iri.startswith(dataset_uri.rstrip("/") + "/"):
                raise SemanticAreaProfilerError(
                    f"Node id is outside dataset_uri: {iri!r}"
                )
            if "#" in iri:
                raise SemanticAreaProfilerError(
                    f"Fragment ids are not allowed in semantic node IDs: {iri!r}"
                )
            if iri in iri_to_node:
                raise SemanticAreaProfilerError(f"Duplicate semantic node ID: {iri!r}")
            iri_to_node[iri] = node

        for iri, node in iri_to_node.items():
            for key, value in node.items():
                if key in {"@id", "@type"}:
                    continue
                if strict_mode and (key.startswith("@") or ":" in key):
                    raise SemanticAreaProfilerError(
                        f"Strict mode rejects non-schema property key: {key!r}"
                    )
                if isinstance(value, dict):
                    raise SemanticAreaProfilerError(
                        f"Inline anonymous objects are not allowed in node {iri!r}."
                    )
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            raise SemanticAreaProfilerError(
                                f"Inline anonymous objects are not allowed in node {iri!r}."
                            )
                        if (
                            strict_mode
                            and isinstance(item, str)
                            and item.startswith("http")
                        ):
                            if item not in iri_to_node and not item.startswith(
                                dataset_uri
                            ):
                                raise SemanticAreaProfilerError(
                                    f"Strict mode rejects external IRI reference: {item!r}"
                                )
                if strict_mode and isinstance(value, str) and value.startswith("http"):
                    is_reference = key not in {"url", "contentUrl", "embedUrl"}
                    if (
                        is_reference
                        and value not in iri_to_node
                        and not value.startswith(dataset_uri)
                    ):
                        raise SemanticAreaProfilerError(
                            f"Strict mode rejects non-dataset IRI reference: {value!r}"
                        )

        for iri, node in iri_to_node.items():
            type_name = self._type_from_node(node)
            rule = self._policy.dependency_rule_for(type_name)
            if rule is None:
                continue
            has_parent_ref = False
            for parent_iri, parent_node in iri_to_node.items():
                for pred in rule.parent_predicates:
                    parent_value = parent_node.get(pred)
                    if parent_value == iri:
                        has_parent_ref = True
                        if not iri.startswith(parent_iri.rstrip("/") + "/"):
                            raise SemanticAreaProfilerError(
                                f"Dependent node {iri!r} must nest under parent {parent_iri!r}."
                            )
                    elif isinstance(parent_value, list) and iri in parent_value:
                        has_parent_ref = True
                        if not iri.startswith(parent_iri.rstrip("/") + "/"):
                            raise SemanticAreaProfilerError(
                                f"Dependent node {iri!r} must nest under parent {parent_iri!r}."
                            )
            if has_parent_ref and not iri.startswith(dataset_uri.rstrip("/") + "/"):
                raise SemanticAreaProfilerError(
                    f"Dependent node outside dataset scope: {iri!r}"
                )

    def _type_priority(self, type_name: str) -> int:
        try:
            return _PAGE_TYPE_PRIORITIES.index(type_name)
        except ValueError:
            return len(_PAGE_TYPE_PRIORITIES)

    def _coherence_label(
        self, best_count: int, runner_up_count: int, total: int
    ) -> str:
        if total < 2:
            return "ambiguous"
        share = best_count / total
        runner_share = runner_up_count / total if total else 0.0
        if best_count >= 2 and share >= _MIN_COHERENT_SHARE and runner_share <= 0.33:
            return "coherent"
        if share <= _MAX_MIXED_SHARE and runner_up_count >= 2:
            return "mixed"
        if share >= _MIN_COHERENT_SHARE and best_count > runner_up_count:
            return "coherent"
        return "ambiguous"

    def _sample_bucket(self, url: str, website_url: str) -> str:
        boundary = self._normalize_boundary(website_url)
        split = urlsplit(url)
        boundary_split = urlsplit(boundary)
        relative = split.path[len(boundary_split.path.rstrip("/")) :].lstrip("/")
        if not relative:
            return "__root__"
        return relative.split("/", 1)[0] or "__root__"

    def _normalize_boundary(self, website_url: str) -> str:
        normalized = website_url.strip().rstrip("/")
        if not normalized:
            raise SemanticAreaProfilerError("website_url is required")
        parsed = urlsplit(normalized)
        if not parsed.scheme or not parsed.netloc:
            raise SemanticAreaProfilerError(
                f"website_url must be an absolute URL prefix: {website_url!r}"
            )
        return normalized

    def _duplicate_indexes(
        self,
        raw_nodes: list[_RawNode],
        incoming: dict[str, list[tuple[str, str | None]]],
    ) -> dict[str, int]:
        grouped: dict[tuple[str, str, str], list[_RawNode]] = defaultdict(list)
        raw_nodes_by_id = {node.raw_id: node for node in raw_nodes}
        for raw_node in raw_nodes:
            if self._first_text(raw_node.properties.get("url")):
                continue
            if self._first_text(raw_node.properties.get("gtin")):
                continue
            parent_key = self._effective_parent_raw_id(
                raw_node=raw_node,
                raw_nodes_by_id=raw_nodes_by_id,
                incoming=incoming,
            )
            node_type = self._preferred_type(raw_node)
            base_slug = (
                normalize_slug(self._slug_source(raw_node, node_type)) or "thing"
            )
            grouped[(parent_key or "__root__", node_type, base_slug)].append(raw_node)

        indexes: dict[str, int] = {}
        for nodes in grouped.values():
            if len(nodes) < 2:
                continue
            for index, node in enumerate(
                sorted(nodes, key=lambda item: item.order), start=1
            ):
                indexes[node.raw_id] = index
        return indexes

    def _effective_parent_raw_id(
        self,
        *,
        raw_node: _RawNode,
        raw_nodes_by_id: dict[str, _RawNode],
        incoming: dict[str, list[tuple[str, str | None]]],
    ) -> str | None:
        if raw_node.parent_raw_id:
            return raw_node.parent_raw_id
        node_type = self._preferred_type(raw_node)
        rule = self._policy.dependency_rule_for(node_type)
        if rule is None:
            return None
        for source_raw_id, source_property in incoming.get(raw_node.raw_id, []):
            if source_property not in rule.parent_predicates:
                continue
            parent = raw_nodes_by_id.get(source_raw_id)
            if parent is None:
                continue
            parent_type = self._preferred_type(parent)
            if parent_type == rule.parent_type or rule.parent_type == "WebPage":
                return source_raw_id
        return None

    def _is_within_boundary(self, url: str, boundary: str) -> bool:
        boundary_split = urlsplit(boundary)
        url_split = urlsplit(url)
        if (
            url_split.scheme != boundary_split.scheme
            or url_split.netloc != boundary_split.netloc
        ):
            return False
        boundary_path = boundary_split.path.rstrip("/")
        candidate_path = url_split.path.rstrip("/")
        if not boundary_path:
            return True
        return candidate_path == boundary_path or candidate_path.startswith(
            boundary_path + "/"
        )

    def _deduplicate_and_sort(self, urls: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for url in sorted(urls, key=self._normalize_url_for_sort):
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
        return out

    def _normalize_url_for_sort(self, url: str) -> str:
        return self._normalize_url(url)

    def _normalize_url_for_hash(self, url: str) -> str:
        normalized = self._normalize_url(url)
        return _sha256_hex(normalized)

    def _normalize_url(self, url: str) -> str:
        split = urlsplit(url)
        query_items = sorted(
            parse_qsl(split.query, keep_blank_values=True),
            key=lambda item: (item[0], item[1]),
        )
        query = urlencode(query_items, doseq=True)
        return urlunsplit((split.scheme, split.netloc, split.path, query, ""))

    def _stable_reference_iri(self, dataset_uri: str, ref_text: str) -> str:
        normalized = ref_text.strip() or "ref"
        return (
            f"{dataset_uri}/{self._policy.container_for_type('Thing')}"
            f"/ref-{_sha256_hex(normalized)}"
        )

    def _slug_source(self, raw_node: _RawNode, node_type: str) -> str:
        for key in ("name", "headline", "title", "gtin", "sku", "value"):
            value = self._first_text(raw_node.properties.get(key))
            if value:
                return value
        return node_type or "Thing"

    def _preferred_type(self, raw_node: _RawNode) -> str:
        types = [type_name for type_name in raw_node.types if type_name]
        if not types:
            return "Thing"
        for candidate in _PAGE_TYPE_PRIORITIES:
            if candidate in types:
                return candidate
        return sorted(types)[0]

    def _needs_stable_index(self, raw_node: _RawNode, slug: str) -> bool:
        # Stable fallback for duplicate base slugs when no URL hash is available.
        return raw_node.parent_raw_id is None and slug != "thing"

    def _page_url(self, raw_node: _RawNode) -> str:
        return raw_node.page_url

    def _first_page_title_hint(self, html: str) -> str | None:
        parser = _PageHtmlParser()
        parser.feed(html)
        return parser.title

    def _first_text(self, value: Any) -> str | None:
        if isinstance(value, list):
            for item in value:
                text = self._first_text(item)
                if text:
                    return text
            return None
        if isinstance(value, dict):
            if "@value" in value:
                return self._first_text(value["@value"])
            if "@id" in value:
                return str(value["@id"]).strip() or None
            return None
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _stringify_value(self, value: Any) -> str | None:
        if isinstance(value, list):
            for item in value:
                text = self._stringify_value(item)
                if text:
                    return text
            return None
        if isinstance(value, dict) and "@id" in value:
            return str(value["@id"])
        return self._first_text(value)

    def _deduplicate_nodes(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in nodes:
            iri = str(node.get("@id") or "")
            if iri in seen:
                continue
            seen.add(iri)
            deduped.append(node)
        return deduped

    def _type_from_node(self, node: dict[str, Any]) -> str:
        raw_type = str(node.get("@type") or "")
        for prefix in ("http://schema.org/", "https://schema.org/", "schema:"):
            if raw_type.startswith(prefix):
                return raw_type[len(prefix) :]
        return raw_type or "Thing"

    def _looks_like_local_file(self, sitemap: str) -> bool:
        path = Path(sitemap)
        return path.exists() and path.is_file()

    def _discover_urls_from_file(self, path: Path) -> list[str]:
        tree = ET.parse(path)
        root = tree.getroot()
        urls: list[str] = []
        for element in root.iter():
            if not element.tag.endswith("loc"):
                continue
            text = (element.text or "").strip()
            if text:
                urls.append(text)
        return urls


def profile_semantic_area(
    *,
    sitemap: str,
    website_url: str,
    url_regex: str | None = None,
    sample_size: int = _DEFAULT_SAMPLE_SIZE,
    sampling_strategy: str = "round_robin_bucket",
    sampling_seed: str | int | None = None,
    inspect_loader: str = "simple",
    inspect_timeout_ms: int = 30_000,
    inspect_retry_attempts: int = 1,
    inspect_retry_backoff_ms: int = 0,
    main_entity_min_confidence: float = 0.6,
    strict_mode: bool = False,
    dataset_uri: str | None = None,
    api_key: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    ssl_ca_cert: str | None = None,
    profiler: SemanticAreaProfiler | None = None,
) -> SemanticAreaProfileResult:
    profiler = profiler or SemanticAreaProfiler()
    request = SemanticAreaProfileRequest(
        sitemap=sitemap,
        website_url=website_url,
        url_regex=url_regex,
        sample_size=sample_size,
        sampling_strategy=sampling_strategy,
        sampling_seed=sampling_seed,
        inspect_loader=inspect_loader,
        inspect_timeout_ms=inspect_timeout_ms,
        inspect_retry_attempts=inspect_retry_attempts,
        inspect_retry_backoff_ms=inspect_retry_backoff_ms,
        main_entity_min_confidence=main_entity_min_confidence,
        strict_mode=strict_mode,
        dataset_uri=dataset_uri,
        api_key=api_key,
        base_url=base_url,
        ssl_ca_cert=ssl_ca_cert,
    )
    return profiler.profile(request)


class _PageHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.title: str | None = None
        self.canonical: str | None = None
        self.meta: dict[str, list[str]] = defaultdict(list)
        self.blocks: list[str] = []
        self._in_title = False
        self._in_jsonld = False
        self._jsonld_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "link":
            rel = attrs_map.get("rel", "").lower()
            href = attrs_map.get("href", "").strip()
            if "canonical" in rel and href:
                self.canonical = href
        elif tag.lower() == "meta":
            key = attrs_map.get("property") or attrs_map.get("name")
            content = attrs_map.get("content", "").strip()
            if key and content:
                self.meta[key.lower()].append(content)
        elif tag.lower() == "script":
            script_type = attrs_map.get("type", "").lower()
            if "ld+json" in script_type:
                self._in_jsonld = True
                self._jsonld_buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_jsonld:
            self._jsonld_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
            title = "".join(self.title_parts).strip()
            self.title = title or self.title
            self.title_parts = []
        elif tag.lower() == "script" and self._in_jsonld:
            self._in_jsonld = False
            payload = "".join(self._jsonld_buffer).strip()
            if payload:
                self.blocks.append(payload)
            self._jsonld_buffer = []


class _PageJsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._in_jsonld = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "script" and "ld+json" in attrs_map.get("type", "").lower():
            self._in_jsonld = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_jsonld:
            self._in_jsonld = False
            payload = "".join(self._buffer).strip()
            if payload:
                self.blocks.append(payload)
            self._buffer = []


def _extract_jsonld_nodes(html: str) -> list[dict[str, Any]]:
    parser = _PageJsonLdParser()
    parser.feed(html)
    nodes: list[dict[str, Any]] = []
    for block in parser.blocks:
        try:
            payload = json.loads(block)
        except Exception:
            continue
        nodes.extend(_iter_jsonld_items(payload))
    return [node for node in nodes if isinstance(node, dict)]


def _iter_jsonld_items(payload: Any) -> Iterable[Any]:
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_jsonld_items(item)
        return
    if not isinstance(payload, dict):
        return
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _iter_jsonld_items(item)
        return
    if "@context" in payload and len(payload) == 1:
        return
    yield payload


def _node_types(node: dict[str, Any]) -> list[str]:
    types = _as_list(node.get("@type"))
    out: list[str] = []
    for raw_type in types:
        if not isinstance(raw_type, str):
            continue
        cleaned = raw_type.strip()
        for prefix in ("http://schema.org/", "https://schema.org/", "schema:"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out or ["Thing"]


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_jsonld_value(
    value: Any,
    *,
    page_index: int,
    parent_raw_id: str,
    source_property: str,
    add_node: Callable[[dict[str, Any], Any], str],
    incoming: dict[str, list[tuple[str, str | None]]],
) -> Any:
    if isinstance(value, list):
        return [
            normalize_jsonld_value(
                item,
                page_index=page_index,
                parent_raw_id=parent_raw_id,
                source_property=source_property,
                add_node=add_node,
                incoming=incoming,
            )
            for item in value
        ]
    if isinstance(value, dict):
        if "@value" in value:
            return value["@value"]
        if set(value.keys()) == {"@id"}:
            ref = str(value["@id"])
            incoming[ref].append((parent_raw_id, source_property))
            return {"@id": ref}
        child_payload = dict(value)
        child_id = add_node(
            child_payload,
            parent_raw_id=parent_raw_id,
            source_property=source_property,
        )
        incoming[child_id].append((parent_raw_id, source_property))
        return {"@id": child_id}
    return value


def _normalize_url(url: str) -> str:
    split = urlsplit(url)
    query_items = sorted(
        parse_qsl(split.query, keep_blank_values=True),
        key=lambda item: (item[0], item[1]),
    )
    query = "&".join(
        f"{key}={value}" if value != "" else f"{key}=" for key, value in query_items
    )
    return urlunsplit((split.scheme, split.netloc, split.path, query, ""))


__all__ = [
    "DatasetUriResolver",
    "JsonLdSemanticDataSerializer",
    "RuntimeDatasetUriResolver",
    "SampledWebPage",
    "SemanticAreaProfileRequest",
    "SemanticAreaProfileResult",
    "SemanticAreaProfiler",
    "SemanticAreaProfilerError",
    "profile_semantic_area",
]

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import hashlib
import json

import pytest

from wordlift_sdk.ingestion.models import LoadedPage, SourceItem
from wordlift_sdk.ingestion.orchestrator import IngestionResult
from wordlift_sdk.ingestion.semantic_area_profiler import (
    SemanticAreaProfileRequest,
    SemanticAreaProfiler,
    SemanticAreaProfilerError,
)

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "semantic_area_profiler"


def _normalized_hash(url: str) -> str:
    split = urlsplit(url)
    query = urlencode(
        sorted(
            parse_qsl(split.query, keep_blank_values=True),
            key=lambda item: (item[0], item[1]),
        ),
        doseq=True,
    )
    normalized = urlunsplit((split.scheme, split.netloc, split.path, query, ""))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class _DiscoveryRecorder:
    def __init__(self, urls: list[str]) -> None:
        self.urls = urls
        self.calls: list[dict[str, object]] = []

    def __call__(self, bundle: dict[str, object]) -> SimpleNamespace:
        self.calls.append(dict(bundle))
        return SimpleNamespace(
            items=[
                SourceItem(id=f"source:{index}", url=url)
                for index, url in enumerate(self.urls, start=1)
            ]
        )


class _FakeOrchestrator:
    def __init__(
        self,
        html_by_url: dict[str, str],
        final_url_by_url: dict[str, str] | None = None,
    ) -> None:
        self.html_by_url = html_by_url
        self.final_url_by_url = final_url_by_url or {}
        self.calls: list[list[str]] = []
        self.configs: list[object] = []

    def run_with_items(self, _config, items):
        self.configs.append(_config)
        selected = [item.url for item in items]
        self.calls.append(selected)
        pages = [
            LoadedPage(
                item_id=item.id,
                url=item.url,
                final_url=self.final_url_by_url.get(item.url, item.url),
                status_code=200,
                html=self.html_by_url[item.url],
                fetch_meta={},
            )
            for item in items
        ]
        return IngestionResult(pages=pages, events=[])


def _load_fixture_pages(name: str) -> tuple[list[str], dict[str, str]]:
    payload = json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))
    pages = payload["pages"]
    urls = [item["url"] for item in pages]
    html_by_url = {item["url"]: item["html"] for item in pages}
    return urls, html_by_url


def _make_article_html(
    *, title: str, canonical: str, page_url: str, org_name: str
) -> str:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": title,
                "url": page_url,
                "author": {"@type": "Person", "name": "Editor"},
                "publisher": {"@type": "Organization", "name": org_name},
            },
            {
                "@type": "Organization",
                "name": org_name,
                "url": "https://example.com/about",
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home"},
                ],
            },
        ],
    }
    return (
        "<html><head>"
        f"<title>{title}</title>"
        f"<link rel='canonical' href='{canonical}' />"
        "<meta property='og:type' content='article' />"
        "</head><body>"
        f"<script type='application/ld+json'>{json.dumps(payload)}</script>"
        "</body></html>"
    )


def _make_generic_html(title: str, page_url: str) -> str:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": title,
                "url": page_url,
            }
        ],
    }
    return (
        "<html><head><title>"
        f"{title}"
        "</title></head><body>"
        f"<script type='application/ld+json'>{json.dumps(payload)}</script>"
        "</body></html>"
    )


def _make_product_html(page_url: str) -> str:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": "Widget page",
                "url": page_url,
            },
            {
                "@type": "Product",
                "name": "Widget 2000",
                "url": "https://example.com/shop/widget?b=2&a=1",
                "gtin": "01234567",
                "offers": {
                    "@type": "Offer",
                    "price": "10.00",
                    "priceSpecification": {
                        "@type": "PriceSpecification",
                        "price": "10.00",
                    },
                },
            },
            {"@type": "ImageObject", "name": "Hero image"},
            {"@type": "ImageObject", "name": "Hero image"},
        ],
    }
    return (
        "<html><head><title>Widget page</title>"
        f"<link rel='canonical' href='{page_url}' />"
        "</head><body>"
        f"<script type='application/ld+json'>{json.dumps(payload)}</script>"
        "</body></html>"
    )


def _make_article_with_unresolved_ref(page_url: str) -> str:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": "Ref article",
                "url": page_url,
                "image": {"@id": "#hero-image"},
            }
        ],
    }
    return (
        "<html><head><title>Ref article</title></head><body>"
        f"<script type='application/ld+json'>{json.dumps(payload)}</script>"
        "</body></html>"
    )


def test_profile_semantic_area_applies_boundary_before_regex_and_samples_deterministically():
    discovery = _DiscoveryRecorder(
        [
            "https://example.com/area/c/1",
            "https://example.com/outside/1",
            "https://example.com/area/a/1",
            "https://example.com/area/b/1",
            "https://example.com/area/a/2",
            "https://example.com/area/b/2",
        ]
    )
    html_by_url = {
        url: _make_article_html(
            title=f"Article {index}",
            canonical=url,
            page_url=url,
            org_name="WordLift",
        )
        for index, url in enumerate(discovery.urls, start=1)
    }
    orchestrator = _FakeOrchestrator(html_by_url)
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    request = SemanticAreaProfileRequest(
        sitemap="https://example.com/sitemap.xml",
        website_url="https://example.com/area",
        url_regex=r"/[abc]/",
        sample_size=3,
        dataset_uri="https://dataset.example",
    )
    result = profiler.profile(request)
    result_again = profiler.profile(request)

    assert discovery.calls == [
        {
            "INGEST_SOURCE": "sitemap",
            "INGEST_LOADER": "simple",
            "SITEMAP_URL": "https://example.com/sitemap.xml",
        },
        {
            "INGEST_SOURCE": "sitemap",
            "INGEST_LOADER": "simple",
            "SITEMAP_URL": "https://example.com/sitemap.xml",
        },
    ]
    assert result.scope == {
        "sitemap": "https://example.com/sitemap.xml",
        "website_url": "https://example.com/area",
        "url_regex": r"/[abc]/",
        "matched_url_count": 5,
        "sample_size": 3,
        "sampled_url_count": 3,
        "sampling_strategy": "round_robin_bucket",
        "sampling_seed": None,
        "inspect_loader": "simple",
    }
    assert [page.url for page in result.sampled_web_pages] == [
        "https://example.com/area/a/1",
        "https://example.com/area/b/1",
        "https://example.com/area/c/1",
    ]
    assert result.to_dict() == result_again.to_dict()


def test_profile_semantic_area_samples_all_when_fewer_than_sample_size_match():
    discovery = _DiscoveryRecorder(
        [
            "https://example.com/area/one",
            "https://example.com/area/two",
        ]
    )
    html_by_url = {
        url: _make_generic_html(title=f"Page {index}", page_url=url)
        for index, url in enumerate(discovery.urls, start=1)
    }
    orchestrator = _FakeOrchestrator(html_by_url)
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/area",
            sample_size=5,
            dataset_uri="https://dataset.example",
        )
    )

    assert result.scope["matched_url_count"] == 2
    assert result.scope["sampled_url_count"] == 2
    assert [page.url for page in result.sampled_web_pages] == discovery.urls
    assert result.main_entity == "WebPage"
    assert result.additional_entity_types == []


def test_profile_semantic_area_falls_back_to_webpage_when_evidence_is_insufficient():
    discovery = _DiscoveryRecorder(["https://example.com/area/one"])
    orchestrator = _FakeOrchestrator(
        {
            "https://example.com/area/one": _make_generic_html(
                "Generic page", "https://example.com/area/one"
            )
        }
    )
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/area",
            dataset_uri="https://dataset.example",
        )
    )

    assert result.main_entity == "WebPage"
    assert result.additional_entity_types == []
    assert result.explanation_metadata["coherence"] == "ambiguous"
    assert (
        "main_entity_reason=no specific type met reliability threshold"
        in result.explanation
    )


def test_profile_semantic_area_identifies_article_and_recurring_support_types():
    urls = [
        "https://example.com/articles/one",
        "https://example.com/articles/two",
    ]
    discovery = _DiscoveryRecorder(urls)
    html_by_url = {
        urls[0]: _make_article_html(
            title="First article",
            canonical=urls[0],
            page_url=urls[0],
            org_name="WordLift",
        ),
        urls[1]: _make_article_html(
            title="Second article",
            canonical=urls[1],
            page_url=urls[1],
            org_name="WordLift",
        ),
    }
    orchestrator = _FakeOrchestrator(html_by_url)
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/articles",
            dataset_uri="https://dataset.example",
        )
    )

    assert result.main_entity == "Article"
    assert "WebPage" not in result.additional_entity_types
    assert "Organization" in result.additional_entity_types
    assert "coherence=coherent" in result.explanation
    assert "main_entity_reason=page votes were {'Article': 2}" in result.explanation
    assert result.sampled_web_pages[0].canonical == urls[0]
    assert result.sampled_web_pages[0].title == "First article"


def test_profile_semantic_area_normalizes_sample_semantic_data_ids():
    url = "https://example.com/shop/widget?b=2&a=1"
    discovery = _DiscoveryRecorder([url])
    orchestrator = _FakeOrchestrator({url: _make_product_html(url)})
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/shop",
            dataset_uri="https://dataset.example",
        )
    )

    graph = result.sample_semantic_data["@graph"]
    ids = [node["@id"] for node in graph]
    assert all(identifier.startswith("https://dataset.example/") for identifier in ids)
    assert all("#" not in identifier for identifier in ids)

    product_id = "https://dataset.example/01/01234567"
    assert any(node["@id"] == product_id for node in graph)
    product_node = next(node for node in graph if node["@id"] == product_id)
    assert product_node["url"] == url
    page_node = next(
        node for node in graph if node["@type"] == "http://schema.org/WebPage"
    )
    assert product_node["mainEntityOfPage"] == page_node["@id"]

    offer_node = next(
        node for node in graph if node["@type"] == "http://schema.org/Offer"
    )
    assert offer_node["@id"].startswith(product_id + "/offers/")
    assert any(
        node["@type"] == "http://schema.org/PriceSpecification" for node in graph
    )
    image_nodes = [
        node for node in graph if node["@type"] == "http://schema.org/ImageObject"
    ]
    assert len(image_nodes) == 2
    assert image_nodes[0]["@id"].endswith("-1")
    assert image_nodes[1]["@id"].endswith("-2")

    expected_hash = _normalized_hash(url)
    assert page_node["@id"].endswith(expected_hash)
    assert page_node["mainEntity"] == product_id


def test_profile_semantic_area_accepts_local_sitemap_files(tmp_path: Path):
    sitemap_path = tmp_path / "sitemap.xml"
    sitemap_path.write_text(
        """<?xml version='1.0' encoding='UTF-8'?>
        <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
          <url><loc>https://example.com/area/one</loc></url>
        </urlset>
        """,
        encoding="utf-8",
    )
    orchestrator = _FakeOrchestrator(
        {
            "https://example.com/area/one": _make_generic_html(
                "Local page", "https://example.com/area/one"
            )
        }
    )

    def _should_not_run(_bundle: dict[str, object]) -> SimpleNamespace:
        raise AssertionError(
            "source discovery should not be called for local sitemap files"
        )

    profiler = SemanticAreaProfiler(
        source_discovery=_should_not_run,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap=str(sitemap_path),
            website_url="https://example.com/area",
            dataset_uri="https://dataset.example",
        )
    )

    assert result.scope["matched_url_count"] == 1
    assert result.sampled_web_pages[0].url == "https://example.com/area/one"


def test_profile_semantic_area_requires_dataset_uri_or_api_key():
    discovery = _DiscoveryRecorder(["https://example.com/area/one"])
    orchestrator = _FakeOrchestrator(
        {
            "https://example.com/area/one": _make_generic_html(
                "Generic page", "https://example.com/area/one"
            )
        }
    )
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    with pytest.raises(SemanticAreaProfilerError, match="dataset_uri is required"):
        profiler.profile(
            SemanticAreaProfileRequest(
                sitemap="https://example.com/sitemap.xml",
                website_url="https://example.com/area",
            )
        )


def test_additional_types_require_recurring_pages_not_duplicate_nodes():
    urls = ["https://example.com/shop/widget", "https://example.com/shop/landing"]
    discovery = _DiscoveryRecorder(urls)
    orchestrator = _FakeOrchestrator(
        {
            urls[0]: _make_product_html(urls[0]),
            urls[1]: _make_generic_html("Landing", urls[1]),
        }
    )
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/shop",
            dataset_uri="https://dataset.example",
        )
    )

    assert "ImageObject" not in result.additional_entity_types


def test_webpage_id_hash_uses_final_url_when_available():
    requested_url = "https://example.com/shop/widget"
    final_url = "https://example.com/shop/widget?z=9&b=2&a=1"
    discovery = _DiscoveryRecorder([requested_url])
    orchestrator = _FakeOrchestrator(
        {requested_url: _make_product_html(requested_url)},
        final_url_by_url={requested_url: final_url},
    )
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/shop",
            dataset_uri="https://dataset.example",
        )
    )

    page_node = next(
        node
        for node in result.sample_semantic_data["@graph"]
        if node["@type"] == "http://schema.org/WebPage"
    )
    assert page_node["url"] == final_url
    assert page_node["@id"].endswith(_normalized_hash(final_url))


def test_unresolved_references_are_mapped_to_dataset_iris():
    url = "https://example.com/articles/ref"
    discovery = _DiscoveryRecorder([url])
    orchestrator = _FakeOrchestrator({url: _make_article_with_unresolved_ref(url)})
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/articles",
            dataset_uri="https://dataset.example",
        )
    )

    article = next(
        node
        for node in result.sample_semantic_data["@graph"]
        if node["@type"] == "http://schema.org/Article"
    )
    assert isinstance(article.get("image"), str)
    assert article["image"].startswith("https://dataset.example/things/ref-")
    assert "#" not in article["image"]


def test_empty_sample_explanation_includes_coherence_and_exclusions():
    discovery = _DiscoveryRecorder(["https://example.com/outside/one"])
    orchestrator = _FakeOrchestrator({})
    profiler = SemanticAreaProfiler(
        source_discovery=discovery,
        orchestrator_factory=lambda: orchestrator,
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/area",
            dataset_uri="https://dataset.example",
        )
    )

    assert result.scope["matched_url_count"] == 0
    assert result.scope["sampled_url_count"] == 0
    assert "coherence=ambiguous" in result.explanation
    assert "notable_exclusions=" in result.explanation


def test_hash_stride_sampling_is_deterministic_with_seed():
    urls = [f"https://example.com/area/{index}" for index in range(1, 10)]
    discovery = _DiscoveryRecorder(urls)
    html_by_url = {
        url: _make_generic_html(f"Page {index}", url)
        for index, url in enumerate(urls, start=1)
    }
    orchestrator = _FakeOrchestrator(html_by_url)
    profiler = SemanticAreaProfiler(
        source_discovery=discovery, orchestrator_factory=lambda: orchestrator
    )

    request = SemanticAreaProfileRequest(
        sitemap="https://example.com/sitemap.xml",
        website_url="https://example.com/area",
        sample_size=4,
        sampling_strategy="hash_stride",
        sampling_seed="stable-seed",
        dataset_uri="https://dataset.example",
    )
    result_one = profiler.profile(request)
    result_two = profiler.profile(request)
    assert [page.url for page in result_one.sampled_web_pages] == [
        page.url for page in result_two.sampled_web_pages
    ]


def test_loader_options_are_forwarded_to_inspection_config():
    url = "https://example.com/area/one"
    discovery = _DiscoveryRecorder([url])
    orchestrator = _FakeOrchestrator({url: _make_generic_html("One", url)})
    profiler = SemanticAreaProfiler(
        source_discovery=discovery, orchestrator_factory=lambda: orchestrator
    )

    profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/area",
            dataset_uri="https://dataset.example",
            inspect_loader="playwright",
            inspect_timeout_ms=12_345,
            inspect_retry_attempts=3,
            inspect_retry_backoff_ms=250,
        )
    )
    cfg = orchestrator.configs[0]
    assert cfg.loader_name == "playwright"
    assert cfg.timeout_ms == 12_345
    assert cfg.retry_attempts == 3
    assert cfg.retry_backoff_ms == 250


def test_passthrough_loader_is_rejected_for_profiler_inspection():
    url = "https://example.com/area/one"
    discovery = _DiscoveryRecorder([url])
    orchestrator = _FakeOrchestrator({url: _make_generic_html("One", url)})
    profiler = SemanticAreaProfiler(
        source_discovery=discovery, orchestrator_factory=lambda: orchestrator
    )

    with pytest.raises(SemanticAreaProfilerError, match="Unsupported inspect_loader"):
        profiler.profile(
            SemanticAreaProfileRequest(
                sitemap="https://example.com/sitemap.xml",
                website_url="https://example.com/area",
                dataset_uri="https://dataset.example",
                inspect_loader="passthrough",
            )
        )


def test_strict_mode_rejects_non_schema_property_keys():
    url = "https://example.com/strict/one"
    html = (
        "<html><head><title>Strict</title></head><body>"
        '<script type=\'application/ld+json\'>{"@context":"https://schema.org","@graph":[{"@type":"Article","headline":"Strict","url":"https://example.com/strict/one","x:custom":"bad"}]}</script>'
        "</body></html>"
    )
    discovery = _DiscoveryRecorder([url])
    orchestrator = _FakeOrchestrator({url: html})
    profiler = SemanticAreaProfiler(
        source_discovery=discovery, orchestrator_factory=lambda: orchestrator
    )

    with pytest.raises(
        SemanticAreaProfilerError, match="Strict mode rejects non-schema property key"
    ):
        profiler.profile(
            SemanticAreaProfileRequest(
                sitemap="https://example.com/sitemap.xml",
                website_url="https://example.com/strict",
                dataset_uri="https://dataset.example",
                strict_mode=True,
            )
        )


def test_fixture_mixed_area_falls_back_to_webpage_when_confidence_is_low():
    urls, html_by_url = _load_fixture_pages("mixed_area.json")
    discovery = _DiscoveryRecorder(urls)
    orchestrator = _FakeOrchestrator(html_by_url)
    profiler = SemanticAreaProfiler(
        source_discovery=discovery, orchestrator_factory=lambda: orchestrator
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/mixed",
            dataset_uri="https://dataset.example",
            main_entity_min_confidence=0.7,
        )
    )
    assert result.main_entity == "WebPage"
    assert result.explanation_metadata["coherence"] in {"mixed", "ambiguous"}


def test_fixture_false_positive_widget_keeps_article_main_entity():
    urls, html_by_url = _load_fixture_pages("false_positive_widget.json")
    discovery = _DiscoveryRecorder(urls)
    orchestrator = _FakeOrchestrator(html_by_url)
    profiler = SemanticAreaProfiler(
        source_discovery=discovery, orchestrator_factory=lambda: orchestrator
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/blog",
            dataset_uri="https://dataset.example",
        )
    )
    assert result.main_entity == "Article"
    assert "Product" in result.additional_entity_types
    assert "main_confidence" in result.explanation_metadata


def test_fixture_ambiguous_area_reports_webpage():
    urls, html_by_url = _load_fixture_pages("ambiguous_area.json")
    discovery = _DiscoveryRecorder(urls)
    orchestrator = _FakeOrchestrator(html_by_url)
    profiler = SemanticAreaProfiler(
        source_discovery=discovery, orchestrator_factory=lambda: orchestrator
    )

    result = profiler.profile(
        SemanticAreaProfileRequest(
            sitemap="https://example.com/sitemap.xml",
            website_url="https://example.com/ambiguous",
            dataset_uri="https://dataset.example",
            main_entity_min_confidence=0.6,
        )
    )
    assert result.main_entity == "WebPage"
    assert result.explanation_metadata["coherence"] in {"mixed", "ambiguous"}

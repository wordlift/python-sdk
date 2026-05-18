from __future__ import annotations

from typing import Any

from .loaders import (
    CrawlerLoaderAdapter,
    PassthroughLoaderAdapter,
    PlaywrightLoaderAdapter,
    PremiumScraperLoaderAdapter,
    ProxyLoaderAdapter,
    SimpleLoaderAdapter,
    WebScrapeApiLoaderAdapter,
)
from .orchestrator import IngestionOrchestrator
from .registry import AdapterRegistry
from .sources import (
    GoogleSheetsSourceAdapter,
    LocalSourceAdapter,
    SitemapSourceAdapter,
    UrlListSourceAdapter,
)


def create_source_registry() -> AdapterRegistry[Any]:
    registry: AdapterRegistry[Any] = AdapterRegistry(kind="source")
    registry.register("urls", UrlListSourceAdapter())
    registry.register("sitemap", SitemapSourceAdapter())
    registry.register("sheets", GoogleSheetsSourceAdapter())
    registry.register("local", LocalSourceAdapter())
    registry.register("debug-cloud", LocalSourceAdapter())
    return registry


def create_loader_registry() -> AdapterRegistry[Any]:
    registry: AdapterRegistry[Any] = AdapterRegistry(kind="loader")
    registry.register("simple", SimpleLoaderAdapter())
    registry.register("proxy", ProxyLoaderAdapter())
    registry.register("playwright", PlaywrightLoaderAdapter())
    registry.register("premium_scraper", PremiumScraperLoaderAdapter())
    registry.register("web_scrape_api", WebScrapeApiLoaderAdapter(mode="default"))
    registry.register("passthrough", PassthroughLoaderAdapter())
    registry.register("crawler", CrawlerLoaderAdapter())
    return registry


def create_orchestrator(**kwargs: Any) -> IngestionOrchestrator:
    return IngestionOrchestrator(
        source_registry=create_source_registry(),
        loader_registry=create_loader_registry(),
        **kwargs,
    )


__all__ = [
    "create_loader_registry",
    "create_orchestrator",
    "create_source_registry",
]

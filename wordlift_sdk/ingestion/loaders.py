from __future__ import annotations

import asyncio
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from wordlift_client import (
    ApiClient,
    WebPageImportFetchOptions,
    WebPageScrapeApi,
    WebPageScrapeRequest,
)

from wordlift_sdk.render import HtmlRenderer, RenderOptions

from .errors import IngestionError, LoaderConfigError, LoaderRuntimeError
from .models import LoadedPage, SourceItem
from .resolver import ResolvedIngestionConfig


class BaseLoaderAdapter:
    def _with_retry(
        self,
        fn: Callable[[], LoadedPage],
        *,
        attempts: int,
        backoff_ms: int,
    ) -> LoadedPage:
        last_exc: Exception | None = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                return fn()
            except IngestionError as exc:
                last_exc = exc
                if not exc.retryable:
                    raise
                if attempt < attempts:
                    time.sleep(max(0, backoff_ms) / 1000.0)
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                if attempt < attempts:
                    time.sleep(max(0, backoff_ms) / 1000.0)

        assert last_exc is not None
        if isinstance(last_exc, LoaderRuntimeError):
            raise last_exc
        raise LoaderRuntimeError(
            str(last_exc),
            code="INGEST_LOAD_NETWORK_ERROR",
            retryable=True,
        ) from last_exc


class PassthroughLoaderAdapter(BaseLoaderAdapter):
    def load(self, item: SourceItem, config: ResolvedIngestionConfig) -> LoadedPage:
        if not item.html:
            raise LoaderRuntimeError(
                "Passthrough loader requires embedded HTML",
                code="INGEST_LOAD_PASSTHROUGH_MISSING_HTML",
                retryable=False,
            )
        return LoadedPage(
            item_id=item.id,
            url=item.url,
            final_url=item.url,
            status_code=200,
            html=item.html,
            fetch_meta={"backend": "passthrough"},
        )


class SimpleLoaderAdapter(BaseLoaderAdapter):
    def load(self, item: SourceItem, config: ResolvedIngestionConfig) -> LoadedPage:
        timeout_sec = max(config.timeout_ms, 1) / 1000.0

        def _run() -> LoadedPage:
            try:
                request = urllib.request.Request(
                    item.url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (X11; Linux x86_64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    },
                )
                with urllib.request.urlopen(request, timeout=timeout_sec) as resp:
                    html_bytes = resp.read()
                    html = html_bytes.decode("utf-8", errors="replace")
                    status = getattr(resp, "status", None)
                    final_url = resp.geturl() if hasattr(resp, "geturl") else item.url
                    return LoadedPage(
                        item_id=item.id,
                        url=item.url,
                        final_url=final_url,
                        status_code=status,
                        html=html,
                        fetch_meta={"backend": "simple"},
                    )
            except urllib.error.URLError as exc:
                raise LoaderRuntimeError(
                    f"Simple loader request failed for {item.url}",
                    code="INGEST_LOAD_NETWORK_ERROR",
                    retryable=True,
                    details={"url": item.url},
                ) from exc

        return self._with_retry(
            _run,
            attempts=config.retry_attempts,
            backoff_ms=config.retry_backoff_ms,
        )


class PlaywrightLoaderAdapter(BaseLoaderAdapter):
    def __init__(self) -> None:
        self._renderer = HtmlRenderer()

    def load(self, item: SourceItem, config: ResolvedIngestionConfig) -> LoadedPage:
        def _run() -> LoadedPage:
            options = RenderOptions(
                url=item.url,
                timeout_ms=config.timeout_ms,
                headless=bool(config.loader_config.get("headless", True)),
                wait_until=str(config.loader_config.get("wait_until", "networkidle")),
            )
            try:
                rendered = self._renderer.render(options)
            except RuntimeError as exc:
                if "Playwright is not installed" in str(exc):
                    raise LoaderConfigError(
                        "Playwright loader selected but Playwright is unavailable",
                        code="INGEST_LOAD_PLAYWRIGHT_UNAVAILABLE",
                        retryable=False,
                    ) from exc
                raise LoaderRuntimeError(
                    f"Playwright loader failed for {item.url}",
                    code="INGEST_LOAD_BROWSER_ERROR",
                    retryable=True,
                ) from exc
            except Exception as exc:
                raise LoaderRuntimeError(
                    f"Playwright loader failed for {item.url}",
                    code="INGEST_LOAD_BROWSER_ERROR",
                    retryable=True,
                ) from exc

            return LoadedPage(
                item_id=item.id,
                url=item.url,
                final_url=item.url,
                status_code=rendered.status_code,
                html=rendered.html,
                fetch_meta={"backend": "playwright", "resources": rendered.resources},
            )

        return self._with_retry(
            _run,
            attempts=config.retry_attempts,
            backoff_ms=config.retry_backoff_ms,
        )


class WebScrapeApiLoaderAdapter(BaseLoaderAdapter):
    def __init__(
        self, *, mode: str | None = None, backend: str = "web_scrape_api"
    ) -> None:
        self._mode = mode
        self._backend = backend

    def load(self, item: SourceItem, config: ResolvedIngestionConfig) -> LoadedPage:
        client_configuration = config.loader_config.get("client_configuration")
        if client_configuration is None:
            raise LoaderConfigError(
                "WORDLIFT_KEY is required for API-backed loaders",
                code="INGEST_CFG_INVALID_OPTION_COMBINATION",
            )

        render_js = config.loader_config.get("render_js")
        wait_for = config.loader_config.get("wait_for")
        country_code = config.loader_config.get("country_code")
        premium_proxy = config.loader_config.get("premium_proxy")
        block_ads = config.loader_config.get("block_ads")

        def _run() -> LoadedPage:
            response = _run_coro_sync(
                self._scrape_async(
                    item_url=item.url,
                    timeout_ms=config.timeout_ms,
                    client_configuration=client_configuration,
                    render_js=render_js,
                    wait_for=wait_for,
                    country_code=country_code,
                    premium_proxy=premium_proxy,
                    block_ads=block_ads,
                )
            )

            web_page = getattr(response, "web_page", None)
            html = getattr(web_page, "html", None)
            if not html:
                raise LoaderRuntimeError(
                    f"API loader returned no HTML for {item.url}",
                    code="INGEST_LOAD_REMOTE_API_ERROR",
                    retryable=True,
                )

            final_url = getattr(web_page, "url", None) or item.url
            status_code = getattr(web_page, "status_code", None)
            fetch_meta = {
                "backend": self._backend,
                "request_id": getattr(response, "id", None),
                "provider_status": getattr(response, "status", None),
                "provider_details": getattr(response, "errors", None),
            }
            return LoadedPage(
                item_id=item.id,
                url=item.url,
                final_url=final_url,
                status_code=status_code,
                html=html,
                fetch_meta=fetch_meta,
            )

        return self._with_retry(
            _run,
            attempts=config.retry_attempts,
            backoff_ms=config.retry_backoff_ms,
        )

    async def _scrape_async(
        self,
        *,
        item_url: str,
        timeout_ms: int,
        client_configuration: Any,
        render_js: Any,
        wait_for: Any,
        country_code: Any,
        premium_proxy: Any,
        block_ads: Any,
    ) -> Any:
        fetch_options = WebPageImportFetchOptions(
            mode=self._mode,
            render_js=render_js,
            wait_for=wait_for,
            country_code=country_code,
            premium_proxy=premium_proxy,
            block_ads=block_ads,
            timeout=timeout_ms,
        )
        async with ApiClient(client_configuration) as client:
            api = WebPageScrapeApi(client)
            response = await api.create_web_page_scrape(
                web_page_scrape_request=WebPageScrapeRequest(
                    url=item_url,
                    fetch_options=fetch_options,
                ),
                _request_timeout=max(timeout_ms, 1) / 1000.0,
            )
            return response


class ProxyLoaderAdapter(WebScrapeApiLoaderAdapter):
    def __init__(self) -> None:
        super().__init__(mode="proxy", backend="proxy")


class PremiumScraperLoaderAdapter(WebScrapeApiLoaderAdapter):
    def __init__(self) -> None:
        super().__init__(mode="premium_scraper", backend="premium_scraper")


def _run_coro_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, Exception] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover
            error["value"] = exc

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result["value"]


__all__ = [
    "BaseLoaderAdapter",
    "PassthroughLoaderAdapter",
    "PlaywrightLoaderAdapter",
    "PremiumScraperLoaderAdapter",
    "ProxyLoaderAdapter",
    "SimpleLoaderAdapter",
    "WebScrapeApiLoaderAdapter",
]

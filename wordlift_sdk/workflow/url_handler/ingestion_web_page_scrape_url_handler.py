from __future__ import annotations

from typing import Any

from wordlift_client import WebPage, WebPageScrapeResponse

from wordlift_sdk.ingestion import run_ingestion

from ...configuration import ConfigurationProvider
from ...protocol import Context, WebPageImportProtocolInterface
from ...url_source import Url
from .url_handler import UrlHandler


class IngestionWebPageScrapeUrlHandler(UrlHandler):
    def __init__(
        self,
        context: Context,
        configuration_provider: ConfigurationProvider,
        web_page_scrape_callback: WebPageImportProtocolInterface,
    ) -> None:
        self._context = context
        self._configuration_provider = configuration_provider
        self._web_page_scrape_callback = web_page_scrape_callback

    async def __call__(self, url: Url) -> None:
        settings = self._build_settings(url)
        result = run_ingestion(settings)

        if not result.pages:
            failed = [
                e for e in result.events if e.get("event") == "ingest.item_failed"
            ]
            if failed:
                first = failed[0]
                raise RuntimeError(
                    f"Ingestion loader failed for {url.value}: {first.get('code')} {first.get('message')}"
                )
            raise RuntimeError(f"Ingestion loader produced no page for {url.value}")

        page = result.pages[0]
        response = WebPageScrapeResponse(
            web_page=WebPage(
                url=page.final_url or page.url,
                html=page.html,
                status_code=page.status_code,
            )
        )
        await self._web_page_scrape_callback.callback(
            response,
            existing_web_page_id=url.iri,
        )

    def _build_settings(self, url: Url) -> dict[str, Any]:
        keys = [
            "WORDLIFT_KEY",
            "API_URL",
            "SSL_CA_CERT",
            "INGEST_LOADER",
            "INGEST_PASSTHROUGH_WHEN_HTML",
            "INGEST_TIMEOUT_MS",
            "INGEST_RETRY_ATTEMPTS",
            "INGEST_RETRY_BACKOFF_MS",
            "WEB_PAGE_IMPORT_MODE",
            "WEB_PAGE_IMPORT_RENDER_JS",
            "WEB_PAGE_IMPORT_WAIT_FOR",
            "WEB_PAGE_IMPORT_COUNTRY_CODE",
            "WEB_PAGE_IMPORT_PREMIUM_PROXY",
            "WEB_PAGE_IMPORT_BLOCK_ADS",
            "WEB_PAGE_IMPORT_TIMEOUT",
            "PLAYWRIGHT_WAIT_UNTIL",
            "PLAYWRIGHT_HEADLESS",
        ]
        settings = {
            key: self._configuration_provider.get_value(key)
            for key in keys
            if self._configuration_provider.get_value(key) is not None
        }
        settings["INGEST_SOURCE"] = "local"
        settings["INGEST_LOCAL_ITEMS"] = [
            {
                "id": url.iri or url.value,
                "url": url.value,
            }
        ]
        return settings

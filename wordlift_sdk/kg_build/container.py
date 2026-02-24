from __future__ import annotations

import logging
from typing import Optional

from wordlift_sdk.container.application_container import ApplicationContainer
from wordlift_sdk.protocol.web_page_import_protocol import (
    WebPageImportProtocolInterface,
)
from wordlift_sdk.workflow.kg_import_workflow import KgImportWorkflow
from wordlift_sdk.workflow.url_handler.default_url_handler import DefaultUrlHandler
from wordlift_sdk.workflow.url_handler.ingestion_web_page_scrape_url_handler import (
    IngestionWebPageScrapeUrlHandler,
)
from wordlift_sdk.workflow.url_handler.url_handler import UrlHandler

logger = logging.getLogger(__name__)


class KgBuildApplicationContainer(ApplicationContainer):
    """Generic application container for KG cloud imports."""

    def __init__(self, configuration_provider):
        super().__init__(configuration_provider)
        self.protocol: Optional[WebPageImportProtocolInterface] = None

    def set_protocol(self, protocol: WebPageImportProtocolInterface):
        self.protocol = protocol

    async def create_web_page_scrape_url_handler(
        self,
    ) -> IngestionWebPageScrapeUrlHandler:
        ingest_loader = self._configuration_provider.get_value(
            "INGEST_LOADER", "web_scrape_api"
        )
        ingest_timeout_ms = self._configuration_provider.get_value(
            "INGEST_TIMEOUT_MS", 30000
        )
        logger.info(
            "Using ingestion bridge config: loader=%s timeout_ms=%s",
            ingest_loader,
            ingest_timeout_ms,
        )
        if self.protocol is None:
            raise RuntimeError(
                "KG build protocol is required before creating handlers."
            )

        return IngestionWebPageScrapeUrlHandler(
            context=await self.get_context(),
            configuration_provider=self._configuration_provider,
            web_page_scrape_callback=self.protocol,
        )

    async def create_kg_import_workflow(self) -> KgImportWorkflow:
        concurrency = self._configuration_provider.get_value("CONCURRENCY", 2)
        url_source = await self.create_new_or_changed_source()

        return KgImportWorkflow(
            context=await self.get_context(),
            url_source=url_source,
            url_handler=await self.create_multi_url_handler(),
            concurrency=concurrency,
        )

    async def create_multi_url_handler(self) -> UrlHandler:
        handlers: list[UrlHandler] = [
            await self.create_web_page_scrape_url_handler(),
        ]
        if (
            self._configuration_provider.get_value("GOOGLE_SEARCH_CONSOLE", True)
            is True
        ):
            handlers.append(await self.create_search_console_url_handler())

        return DefaultUrlHandler(url_handler_list=handlers)

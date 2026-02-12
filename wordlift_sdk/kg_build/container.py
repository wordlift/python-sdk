from __future__ import annotations

import logging
from typing import Optional

from wordlift_sdk.container.application_container import ApplicationContainer
from wordlift_sdk.protocol.web_page_import_protocol import (
    WebPageImportProtocolInterface,
)
from wordlift_sdk.workflow.kg_import_workflow import KgImportWorkflow
from wordlift_sdk.workflow.url_handler import WebPageImportUrlHandler
from wordlift_sdk.workflow.url_handler.web_page_import_url_handler import (
    WebPageImportFetchOptions,
)

logger = logging.getLogger(__name__)


class KgBuildApplicationContainer(ApplicationContainer):
    """Generic application container for KG cloud imports."""

    def __init__(self, configuration_provider):
        super().__init__(configuration_provider)
        self.protocol: Optional[WebPageImportProtocolInterface] = None

    def set_protocol(self, protocol: WebPageImportProtocolInterface):
        self.protocol = protocol

    async def create_web_page_import_url_handler(self) -> WebPageImportUrlHandler:
        write_strategy = self._configuration_provider.get_value(
            "WEB_PAGE_IMPORT_WRITE_STRATEGY", "createOrUpdateModel"
        )

        fetch_options = WebPageImportFetchOptions(
            mode=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_MODE", "default"
            ),
            render_js=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_RENDER_JS", None
            ),
            wait_for=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_WAIT_FOR", None
            ),
            country_code=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_COUNTRY_CODE", None
            ),
            premium_proxy=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_PREMIUM_PROXY", None
            ),
            block_ads=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_BLOCK_ADS", None
            ),
            timeout=self._configuration_provider.get_value(
                "WEB_PAGE_IMPORT_TIMEOUT", None
            ),
        )
        logger.info("Using Cloud Fetch Options: %s", fetch_options)

        return WebPageImportUrlHandler(
            context=await self.get_context(),
            embedding_properties=self._configuration_provider.get_value(
                "EMBEDDING_PROPERTIES",
                [
                    "http://schema.org/headline",
                    "http://schema.org/abstract",
                    "http://schema.org/text",
                ],
            ),
            web_page_types=self._configuration_provider.get_value(
                "WEB_PAGE_TYPES", ["http://schema.org/Article"]
            ),
            write_strategy=write_strategy,
            fetch_options=fetch_options,
            web_page_import_callback=self.protocol,
        )

    async def create_kg_import_workflow(self) -> KgImportWorkflow:
        concurrency = self._configuration_provider.get_value("CONCURRENCY", 2)
        url_source = await self.create_new_or_changed_source()

        return KgImportWorkflow(
            context=await self.get_context(),
            url_source=url_source,
            url_handler=await self.create_web_page_import_url_handler(),
            concurrency=concurrency,
        )

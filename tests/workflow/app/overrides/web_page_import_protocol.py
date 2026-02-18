from wordlift_sdk.protocol import WebPageImportProtocolInterface


class WebPageImportProtocol(WebPageImportProtocolInterface):
    async def callback(
        self, web_page_import_response, existing_web_page_id: str | None = None
    ) -> None:
        pass

from wordlift_sdk.protocol import WebPageImportProtocolInterface
from wordlift_client import WebPageImportResponse


class WebPageImportProtocol(WebPageImportProtocolInterface):

    async def callback(self, web_page_import_response: WebPageImportResponse) -> None:
        pass

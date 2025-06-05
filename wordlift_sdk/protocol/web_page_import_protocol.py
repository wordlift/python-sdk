from abc import abstractmethod

from .context import Context

from typing import Protocol
from wordlift_client import WebPageImportResponse


class WebPageImportProtocolInterface(Protocol):
    context: Context

    def __init__(self, context: Context):
        self.context = context

    @abstractmethod
    async def callback(self, web_page_import_response: WebPageImportResponse) -> None:
        pass


class DefaultWebPageImportProtocol(WebPageImportProtocolInterface):

    async def callback(self, web_page_import_response: WebPageImportResponse) -> None:
        pass

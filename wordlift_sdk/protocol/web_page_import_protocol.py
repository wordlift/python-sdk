from abc import abstractmethod

from .context import Context

from typing import Any, Protocol


class WebPageImportProtocolInterface(Protocol):
    context: Context

    def __init__(self, context: Context):
        self.context = context

    @abstractmethod
    async def callback(
        self,
        response: Any,
        existing_web_page_id: str | None = None,
    ) -> None:
        pass


class DefaultWebPageImportProtocol(WebPageImportProtocolInterface):
    async def callback(
        self,
        response: Any,
        existing_web_page_id: str | None = None,
    ) -> None:
        pass

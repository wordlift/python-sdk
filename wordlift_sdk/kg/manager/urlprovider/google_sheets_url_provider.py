from typing import AsyncGenerator

from .url_provider import UrlProvider, Url


class GoogleSheetsUrlProvider(UrlProvider):
    def __init__(self, url: str):
        pass

    async def urls(self) -> AsyncGenerator[Url, None]:
        pass

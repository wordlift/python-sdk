from typing import AsyncGenerator

from .url_provider import UrlProvider, Url


class ListUrlProvider(UrlProvider):
    def __init__(self, urls: list[str]):
        self.urls = urls

    async def urls(self) -> AsyncGenerator[Url, None]:
        for url in self.urls:
            yield Url(value=url)

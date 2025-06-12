from abc import ABC

from ...url_source import Url


class UrlHandler(ABC):
    async def __call__(self, url: Url):
        pass

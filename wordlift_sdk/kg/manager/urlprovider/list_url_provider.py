from typing import AsyncGenerator

from .url_provider import UrlProvider, Url


class ListUrlProvider(UrlProvider):
    """A URL provider that yields URLs from a predefined list.

    This provider takes a list of URL strings and provides them one by one
    through the async generator method `urls()`.
    """

    def __init__(self, urls: list[str]):
        """Initialize the ListUrlProvider with a list of URLs.

        Args:
            urls: A list of URL strings to be provided.
        """
        self.urls = urls

    async def urls(self) -> AsyncGenerator[Url, None]:
        """Asynchronously yield Url objects from the predefined list.

        Yields:
            Url: A Url object for each URL string in the list.
        """
        for url in self.urls:
            yield Url(value=url)

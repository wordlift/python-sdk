from typing import AsyncGenerator

from .url_source import UrlSource, Url


class ListUrlSource(UrlSource):
    """A URL provider that yields URLs from a predefined list.

    This provider takes a list of URL strings and provides them one by one
    through the async generator method `urls()`.
    """

    def __init__(self, urls: list[str]):
        """Initialize the ListUrlProvider with a list of URLs.

        Args:
            urls: A list of URL strings to be provided.
        """
        self._url_list = urls

    async def urls(self) -> AsyncGenerator[Url, None]:
        """Asynchronously yield Url objects from the predefined list.

        Yields:
            Url: A Url object for each URL string in the list.
        """
        for url in self._url_list:
            yield Url(value=url)

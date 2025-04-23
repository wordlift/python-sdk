from typing import AsyncGenerator

import advertools as adv

from .url_provider import UrlProvider, Url


class SitemapUrlProvider(UrlProvider):
    """
    A URL provider that extracts URLs from a sitemap.

    This class implements the UrlProvider interface to provide URLs from a sitemap file.
    It uses the advertools library to parse the sitemap and extract the URLs from the 'loc' column.
    """

    def __init__(self, sitemap_url: str):
        """
        Initialize the SitemapUrlProvider with a sitemap URL.

        Args:
            sitemap_url (str): The URL of the sitemap to extract URLs from.
        """
        self.sitemap_url = sitemap_url

    async def urls(self) -> AsyncGenerator[Url, None]:
        """
        Asynchronously yield URLs from the sitemap.

        This method fetches the sitemap from the provided URL, extracts all URLs from the 'loc' column,
        and yields them one by one as Url objects.

        Returns:
            AsyncGenerator[Url, None]: An asynchronous generator that yields Url objects.
        """
        # Get the list of URLs from the sitemap (`loc` column)
        sitemap_df = adv.sitemap_to_df(self.sitemap_url)
        urls = set(sitemap_df['loc'])

        for url in urls:
            yield Url(value=url)

from typing import AsyncGenerator

import advertools as adv

from .url_provider import UrlProvider, Url


class SitemapUrlProvider(UrlProvider):
    def __init__(self, sitemap_url: str):
        self.sitemap_url = sitemap_url

    async def urls(self) -> AsyncGenerator[Url, None]:
        # Get the list of URLs from the sitemap (`loc` column)
        sitemap_df = adv.sitemap_to_df(self.sitemap_url)
        urls = set(sitemap_df['loc'])

        for url in urls:
            yield Url(value=url)

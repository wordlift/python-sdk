import re
from typing import AsyncGenerator, Optional

import advertools as adv
import pandas as pd

from .url_source import UrlSource, Url


class SitemapUrlSource(UrlSource):
    sitemap_url: str
    pattern: re.Pattern | None

    def __init__(self, sitemap_url: str, pattern: Optional[re.Pattern] = None):
        self.pattern = pattern
        self.sitemap_url = sitemap_url

    async def urls(self) -> AsyncGenerator[Url, None]:
        sitemap_df = adv.sitemaps.sitemap_to_df(sitemap_url=self.sitemap_url)
        # Ensure 'lastmod' column exists
        if "lastmod" not in sitemap_df.columns:
            sitemap_df["lastmod"] = None
        sitemap_df["lastmod_as_datetime"] = pd.to_datetime(
            sitemap_df["lastmod"], errors="coerce"
        )

        for _, row in sitemap_df.iterrows():
            url = row["loc"]
            last_mod_as_datetime = row["lastmod_as_datetime"]
            if self.pattern is None or self.pattern.search(url):
                yield Url(
                    value=url,
                    date_modified=None
                    if pd.isna(last_mod_as_datetime)
                    else last_mod_as_datetime.to_pydatetime(),
                )

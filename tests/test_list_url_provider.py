import asyncio
import unittest
from typing import List

from wordlift_sdk.url_source import ListUrlSource, Url


class TestListUrlSource(unittest.TestCase):
    def test_init(self):
        """Test that the ListUrlSource is initialized correctly with a list of URLs."""
        url_list = ["https://example.com/page1", "https://example.com/page2"]
        provider = ListUrlSource(url_list)

        self.assertEqual(provider._url_list, url_list)

    def test_urls_method(self):
        """Test that the urls method yields Url objects for each URL in the list."""
        url_list = ["https://example.com/page1", "https://example.com/page2"]
        provider = ListUrlSource(url_list)

        # Run the async generator and collect the results
        result_urls = asyncio.run(self._collect_urls(provider))

        # Check that we got the expected number of URLs
        self.assertEqual(len(result_urls), len(url_list))

        # Check that each URL is a Url object with the expected value
        for i, url in enumerate(result_urls):
            self.assertIsInstance(url, Url)
            self.assertEqual(url.value, url_list[i])

    def test_empty_list(self):
        """Test that the urls method works correctly with an empty list."""
        provider = ListUrlSource([])

        # Run the async generator and collect the results
        result_urls = asyncio.run(self._collect_urls(provider))

        # Check that we got an empty list
        self.assertEqual(len(result_urls), 0)

    async def _collect_urls(self, provider: ListUrlSource) -> List[Url]:
        """Helper method to collect URLs from the async generator."""
        result_urls = []
        async for url in provider.urls():
            result_urls.append(url)
        return result_urls


if __name__ == "__main__":
    unittest.main()

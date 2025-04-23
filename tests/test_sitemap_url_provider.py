import unittest
import asyncio
import pandas as pd
from unittest.mock import patch, MagicMock
from typing import List

from wordlift_sdk.kg.manager.urlprovider import SitemapUrlProvider
from wordlift_sdk.kg.manager.urlprovider.url_provider import Url


class TestSitemapUrlProvider(unittest.TestCase):
    def test_init(self):
        """Test that the SitemapUrlProvider is initialized correctly with a sitemap URL."""
        sitemap_url = "https://example.com/sitemap.xml"
        provider = SitemapUrlProvider(sitemap_url)
        
        self.assertEqual(provider.sitemap_url, sitemap_url)
    
    @patch('wordlift_sdk.kg.manager.urlprovider.sitemap_url_provider.adv')
    def test_urls_method(self, mock_adv):
        """Test that the urls method yields Url objects for each URL in the sitemap."""
        # Mock the sitemap_to_df function to return a dataframe with URLs
        mock_df = pd.DataFrame({
            'loc': ['https://example.com/page1', 'https://example.com/page2', 'https://example.com/page2']  # Duplicate URL to test set behavior
        })
        mock_adv.sitemap_to_df.return_value = mock_df
        
        sitemap_url = "https://example.com/sitemap.xml"
        provider = SitemapUrlProvider(sitemap_url)
        
        # Run the async generator and collect the results
        result_urls = asyncio.run(self._collect_urls(provider))
        
        # Check that mock was called with the correct sitemap URL
        mock_adv.sitemap_to_df.assert_called_once_with(sitemap_url)
        
        # Check that we got the expected number of URLs (should be 2, as duplicates are removed)
        self.assertEqual(len(result_urls), 2)
        
        # Check that each URL is a Url object with the expected value
        expected_urls = {'https://example.com/page1', 'https://example.com/page2'}
        actual_urls = {url.value for url in result_urls}
        self.assertEqual(actual_urls, expected_urls)
    
    @patch('wordlift_sdk.kg.manager.urlprovider.sitemap_url_provider.adv')
    def test_empty_sitemap(self, mock_adv):
        """Test that the urls method works correctly with an empty sitemap."""
        # Mock the sitemap_to_df function to return an empty dataframe
        mock_df = pd.DataFrame({'loc': []})
        mock_adv.sitemap_to_df.return_value = mock_df
        
        sitemap_url = "https://example.com/sitemap.xml"
        provider = SitemapUrlProvider(sitemap_url)
        
        # Run the async generator and collect the results
        result_urls = asyncio.run(self._collect_urls(provider))
        
        # Check that we got an empty list
        self.assertEqual(len(result_urls), 0)
    
    async def _collect_urls(self, provider: SitemapUrlProvider) -> List[Url]:
        """Helper method to collect URLs from the async generator."""
        result_urls = []
        async for url in provider.urls():
            result_urls.append(url)
        return result_urls


if __name__ == "__main__":
    unittest.main()
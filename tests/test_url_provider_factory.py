import unittest
from unittest.mock import MagicMock

from wordlift_sdk.kg.manager.urlprovider import (
    UrlProviderFactory,
    UrlProviderFactoryInput,
    UrlProvider
)
from wordlift_sdk.kg.manager.urlprovider.sitemap_url_provider import SitemapUrlProvider
from wordlift_sdk.kg.manager.urlprovider.google_sheets_url_provider import GoogleSheetsUrlProvider
from wordlift_sdk.kg.manager.urlprovider.list_url_provider import ListUrlProvider


class TestUrlProviderFactory(unittest.TestCase):
    def test_create_sitemap_provider(self):
        # Test that SitemapUrlProvider is created when sitemap_url is provided
        input_params = UrlProviderFactoryInput(sitemap_url="https://example.com/sitemap.xml")
        provider = UrlProviderFactory.create(input_params)

        self.assertIsInstance(provider, SitemapUrlProvider)
        self.assertEqual(provider.sitemap_url, "https://example.com/sitemap.xml")

    def test_create_google_sheets_provider(self):
        # Test that GoogleSheetsUrlProvider is created when sheets parameters are provided
        mock_creds = MagicMock()
        input_params = UrlProviderFactoryInput(
            sheets_url="https://docs.google.com/spreadsheets/d/example",
            sheets_name="Sheet1",
            sheets_creds_or_client=mock_creds
        )
        provider = UrlProviderFactory.create(input_params)

        self.assertIsInstance(provider, GoogleSheetsUrlProvider)
        self.assertEqual(provider.url, "https://docs.google.com/spreadsheets/d/example")
        self.assertEqual(provider.sheet, "Sheet1")
        self.assertEqual(provider.creds_or_client, mock_creds)

    def test_create_list_provider(self):
        # Test that ListUrlProvider is created when urls is provided
        urls = ["https://example.com/page1", "https://example.com/page2"]
        input_params = UrlProviderFactoryInput(urls=urls)
        provider = UrlProviderFactory.create(input_params)

        self.assertIsInstance(provider, ListUrlProvider)
        self.assertEqual(provider._url_list, urls)

    def test_provider_preference_order(self):
        # Test that providers are created in the correct order of preference
        # When multiple parameters are provided, SitemapUrlProvider should be preferred
        input_params = UrlProviderFactoryInput(
            sitemap_url="https://example.com/sitemap.xml",
            urls=["https://example.com/page1"]
        )
        provider = UrlProviderFactory.create(input_params)

        self.assertIsInstance(provider, SitemapUrlProvider)

        # When sitemap_url is not provided but sheets parameters are,
        # GoogleSheetsUrlProvider should be preferred over ListUrlProvider
        mock_creds = MagicMock()
        input_params = UrlProviderFactoryInput(
            sheets_url="https://docs.google.com/spreadsheets/d/example",
            sheets_name="Sheet1",
            sheets_creds_or_client=mock_creds,
            urls=["https://example.com/page1"]
        )
        provider = UrlProviderFactory.create(input_params)

        self.assertIsInstance(provider, GoogleSheetsUrlProvider)

    def test_no_parameters_raises_error(self):
        # Test that ValueError is raised when no parameters are provided
        input_params = UrlProviderFactoryInput()

        with self.assertRaises(ValueError):
            UrlProviderFactory.create(input_params)

    def test_incomplete_sheets_parameters(self):
        # Test that ListUrlProvider is created when sheets parameters are incomplete
        # but urls is provided
        input_params = UrlProviderFactoryInput(
            sheets_url="https://docs.google.com/spreadsheets/d/example",
            # Missing sheets_name and sheets_creds_or_client
            urls=["https://example.com/page1"]
        )
        provider = UrlProviderFactory.create(input_params)

        self.assertIsInstance(provider, ListUrlProvider)


if __name__ == "__main__":
    unittest.main()

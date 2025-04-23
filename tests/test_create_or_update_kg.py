import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from wordlift_client import Configuration

from wordlift_sdk.kg.manager.urlprovider.url_provider import UrlProvider, Url
from wordlift_sdk.kg.manager.urlprovider.list_url_provider import ListUrlProvider
from wordlift_sdk.kg.manager.urlprovider.sitemap_url_provider import SitemapUrlProvider
from wordlift_sdk.utils.create_or_update_kg import (
    create_or_update_kg_using_url_provider,
    create_or_update_kg_using_urls,
    create_or_update_kg_using_sitemap
)


class TestCreateOrUpdateKg(unittest.TestCase):
    def setUp(self):
        self.configuration = Configuration()
        self.key = "test_key"
        self.types = {"Article", "WebPage"}
        self.concurrency = 2
        self.urls = {"https://example.com/page1", "https://example.com/page2"}
        self.sitemap_url = "https://example.com/sitemap.xml"

    @patch('wordlift_sdk.utils.create_or_update_kg.create_dataframe_of_entities_by_types')
    @patch('wordlift_sdk.utils.create_or_update_kg.create_dataframe_of_url_iri')
    @patch('wordlift_sdk.utils.create_or_update_kg.import_url_factory')
    @patch('wordlift_sdk.utils.create_or_update_kg.tqdm.gather')
    @patch('wordlift_sdk.utils.create_or_update_kg.entity.enrich')
    async def test_create_or_update_kg_using_url_provider(
        self, mock_enrich, mock_gather, mock_import_url_factory, 
        mock_create_dataframe_of_url_iri, mock_create_dataframe_of_entities_by_types
    ):
        # Create a mock UrlProvider
        mock_url_provider = MagicMock(spec=UrlProvider)
        mock_url_provider.urls = AsyncMock()
        mock_url_provider.urls.return_value.__aiter__.return_value = [
            Url(value="https://example.com/page1"),
            Url(value="https://example.com/page2")
        ]

        # Mock the dataframe returned by create_dataframe_of_entities_by_types
        mock_kg_df = MagicMock()
        mock_kg_df.__getitem__.return_value = []
        mock_create_dataframe_of_entities_by_types.return_value = mock_kg_df

        # Mock the import_url_factory
        mock_import_url = AsyncMock()
        mock_import_url_factory.return_value = mock_import_url

        # Call the function
        await create_or_update_kg_using_url_provider(
            configuration=self.configuration,
            key=self.key,
            url_provider=mock_url_provider,
            types=self.types,
            concurrency=self.concurrency
        )

        # Verify that the url_provider.urls method was called
        mock_url_provider.urls.assert_called_once()

        # Verify that create_dataframe_of_entities_by_types was called with the correct parameters
        mock_create_dataframe_of_entities_by_types.assert_called_once_with(
            key=self.key, types=self.types
        )

        # Verify that import_url_factory was called with the correct parameters
        mock_import_url_factory.assert_called_once_with(
            configuration=self.configuration, types=self.types
        )

        # Verify that gather was called for importing URLs
        mock_gather.assert_called()

    @patch('wordlift_sdk.utils.create_or_update_kg.create_or_update_kg_using_url_provider')
    async def test_create_or_update_kg_using_urls(self, mock_create_or_update_kg_using_url_provider):
        # Set up the mock as an AsyncMock
        mock_create_or_update_kg_using_url_provider.side_effect = AsyncMock()

        # Call the function
        await create_or_update_kg_using_urls(
            configuration=self.configuration,
            key=self.key,
            urls=self.urls,
            types=self.types,
            concurrency=self.concurrency
        )

        # Verify that create_or_update_kg_using_url_provider was called with the correct parameters
        mock_create_or_update_kg_using_url_provider.assert_called_once()
        args, kwargs = mock_create_or_update_kg_using_url_provider.call_args

        # Check that the url_provider is a ListUrlProvider with the correct URLs
        self.assertIsInstance(kwargs['url_provider'], ListUrlProvider)
        self.assertEqual(set(kwargs['url_provider']._url_list), self.urls)

        # Check other parameters
        self.assertEqual(kwargs['configuration'], self.configuration)
        self.assertEqual(kwargs['key'], self.key)
        self.assertEqual(kwargs['types'], self.types)
        self.assertEqual(kwargs['concurrency'], self.concurrency)

    @patch('wordlift_sdk.utils.create_or_update_kg.adv.sitemap_to_df')
    @patch('wordlift_sdk.utils.create_or_update_kg.create_or_update_kg_using_url_provider')
    async def test_create_or_update_kg_using_sitemap(
        self, mock_create_or_update_kg_using_url_provider, mock_sitemap_to_df
    ):
        # Set up the mock as an AsyncMock
        mock_create_or_update_kg_using_url_provider.side_effect = AsyncMock()

        # Mock the sitemap_to_df function to return a dataframe with a 'loc' column
        mock_df = MagicMock()
        mock_df.__getitem__.return_value = list(self.urls)
        mock_sitemap_to_df.return_value = mock_df

        # Call the function
        await create_or_update_kg_using_sitemap(
            configuration=self.configuration,
            key=self.key,
            sitemap_url=self.sitemap_url,
            types=self.types,
            concurrency=self.concurrency
        )

        # Verify that create_or_update_kg_using_url_provider was called with the correct parameters
        mock_create_or_update_kg_using_url_provider.assert_called_once()
        args, kwargs = mock_create_or_update_kg_using_url_provider.call_args

        # Check that the url_provider is a SitemapUrlProvider with the correct sitemap URL
        self.assertIsInstance(kwargs['url_provider'], SitemapUrlProvider)
        self.assertEqual(kwargs['url_provider'].sitemap_url, self.sitemap_url)

        # Check other parameters
        self.assertEqual(kwargs['configuration'], self.configuration)
        self.assertEqual(kwargs['key'], self.key)
        self.assertEqual(kwargs['types'], self.types)
        self.assertEqual(kwargs['concurrency'], self.concurrency)


if __name__ == "__main__":
    unittest.main()

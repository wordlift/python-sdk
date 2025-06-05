import asyncio
import unittest
from typing import List
from unittest.mock import patch, MagicMock

import pandas as pd

from wordlift_sdk.url_source import GoogleSheetsUrlSource, Url


class TestGoogleSheetsUrlSource(unittest.TestCase):
    def test_init(self):
        """Test that the GoogleSheetsUrlSource is initialized correctly."""
        mock_creds = MagicMock()
        url = "https://docs.google.com/spreadsheets/d/example"
        sheet = "Sheet1"
        provider = GoogleSheetsUrlSource(mock_creds, url, sheet)

        self.assertEqual(provider.creds_or_client, mock_creds)
        self.assertEqual(provider.url, url)
        self.assertEqual(provider.sheet, sheet)

    @patch('wordlift_sdk.url_source.google_sheets_url_source.create_dataframe_from_google_sheets')
    def test_urls_method(self, mock_create_df):
        """Test that the urls method yields Url objects for each URL in the sheet."""
        # Mock the create_dataframe_from_google_sheets function to return a dataframe with URLs
        mock_df = pd.DataFrame({
            'url': ['https://example.com/page1', 'https://example.com/page2', '']  # Include empty URL to test filtering
        })
        mock_create_df.return_value = mock_df

        mock_creds = MagicMock()
        url = "https://docs.google.com/spreadsheets/d/example"
        sheet = "Sheet1"
        provider = GoogleSheetsUrlSource(mock_creds, url, sheet)

        # Run the async generator and collect the results
        result_urls = asyncio.run(self._collect_urls(provider))

        # Check that mock was called with the correct parameters
        mock_create_df.assert_called_once_with(mock_creds, url, sheet)

        # Check that we got the expected number of URLs (should be 2, as empty URL is filtered out)
        self.assertEqual(len(result_urls), 2)

        # Check that each URL is a Url object with the expected value
        expected_urls = ['https://example.com/page1', 'https://example.com/page2']
        for i, url in enumerate(result_urls):
            self.assertIsInstance(url, Url)
            self.assertEqual(url.value, expected_urls[i])

    @patch('wordlift_sdk.url_source.google_sheets_url_source.create_dataframe_from_google_sheets')
    def test_empty_sheet(self, mock_create_df):
        """Test that the urls method works correctly with an empty sheet."""
        # Mock the create_dataframe_from_google_sheets function to return an empty dataframe
        mock_df = pd.DataFrame({'url': []})
        mock_create_df.return_value = mock_df

        mock_creds = MagicMock()
        url = "https://docs.google.com/spreadsheets/d/example"
        sheet = "Sheet1"
        provider = GoogleSheetsUrlSource(mock_creds, url, sheet)

        # Run the async generator and collect the results
        result_urls = asyncio.run(self._collect_urls(provider))

        # Check that we got an empty list
        self.assertEqual(len(result_urls), 0)

    @patch('wordlift_sdk.url_source.google_sheets_url_source.create_dataframe_from_google_sheets')
    def test_missing_url_column(self, mock_create_df):
        """Test that ValueError is raised when the 'url' column is missing."""
        # Mock the create_dataframe_from_google_sheets function to return a dataframe without 'url' column
        mock_df = pd.DataFrame({'other_column': ['value1', 'value2']})
        mock_create_df.return_value = mock_df

        mock_creds = MagicMock()
        url = "https://docs.google.com/spreadsheets/d/example"
        sheet = "Sheet1"
        provider = GoogleSheetsUrlSource(mock_creds, url, sheet)

        # Check that ValueError is raised when trying to get URLs
        with self.assertRaises(ValueError):
            asyncio.run(self._collect_urls(provider))

    @patch('wordlift_sdk.url_source.google_sheets_url_source.create_dataframe_from_google_sheets')
    def test_nan_values(self, mock_create_df):
        """Test that NaN values are filtered out."""
        # Mock the create_dataframe_from_google_sheets function to return a dataframe with NaN values
        mock_df = pd.DataFrame({
            'url': ['https://example.com/page1', pd.NA, 'https://example.com/page2']
        })
        mock_create_df.return_value = mock_df

        mock_creds = MagicMock()
        url = "https://docs.google.com/spreadsheets/d/example"
        sheet = "Sheet1"
        provider = GoogleSheetsUrlSource(mock_creds, url, sheet)

        # Run the async generator and collect the results
        result_urls = asyncio.run(self._collect_urls(provider))

        # Check that we got the expected number of URLs (should be 2, as NaN is filtered out)
        self.assertEqual(len(result_urls), 2)

        # Check that each URL is a Url object with the expected value
        expected_urls = ['https://example.com/page1', 'https://example.com/page2']
        for i, url in enumerate(result_urls):
            self.assertIsInstance(url, Url)
            self.assertEqual(url.value, expected_urls[i])

    async def _collect_urls(self, provider: GoogleSheetsUrlSource) -> List[Url]:
        """Helper method to collect URLs from the async generator."""
        result_urls = []
        async for url in provider.urls():
            result_urls.append(url)
        return result_urls


if __name__ == "__main__":
    unittest.main()

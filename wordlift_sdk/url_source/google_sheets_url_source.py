from typing import AsyncGenerator

import pandas as pd
from google.auth.credentials import Credentials
from gspread import Client

from .url_source import UrlSource, Url
from ..utils.create_dataframe_from_google_sheets import create_dataframe_from_google_sheets


class GoogleSheetsUrlSource(UrlSource):
    """
    A URL provider that extracts URLs from a Google Sheet.

    This class implements the UrlProvider interface to provide URLs from a Google Sheet.
    It uses the create_dataframe_from_google_sheets function to fetch the sheet data
    and extracts the URLs from the 'url' column.
    """

    def __init__(self, creds_or_client: Credentials | Client, url: str, sheet: str):
        """
        Initialize the GoogleSheetsUrlProvider with Google Sheets credentials and URL.

        Args:
            creds_or_client (Credentials | Client): Google Auth Credentials or gspread Client
            url (str): The URL of the Google Sheet
            sheet (str): The name of the worksheet
        """
        self.creds_or_client = creds_or_client
        self.url = url
        self.sheet = sheet

    async def urls(self) -> AsyncGenerator[Url, None]:
        """
        Asynchronously yield URLs from the Google Sheet.

        This method fetches the Google Sheet data using the create_dataframe_from_google_sheets function,
        and yields each URL from the 'url' column as a Url object.

        Returns:
            AsyncGenerator[Url, None]: An asynchronous generator that yields Url objects.
        """
        # Get the dataframe from the Google Sheet
        df = create_dataframe_from_google_sheets(self.creds_or_client, self.url, self.sheet)

        # Check if 'url' column exists
        if 'url' not in df.columns:
            raise ValueError("The Google Sheet must contain a 'url' column")

        # Yield each URL from the 'url' column
        for url in df['url']:
            if pd.notna(url) and url.strip():  # Skip empty or NaN values
                yield Url(value=url.strip())

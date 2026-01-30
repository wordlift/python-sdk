import logging
import os
from typing import Optional, Any, Dict

import gspread
from wordlift_sdk.configuration import ConfigurationProvider

logger = logging.getLogger(__name__)


class GoogleSheetsLookup:
    """
    A generic class to lookup values from a Google Sheet.
    Preloads data upon initialization for O(1) lookup performance.
    """

    def __init__(
        self,
        spreadsheet_url: str,
        sheet_name: str,
        key_column: str,
        value_column: str,
        configuration_provider: ConfigurationProvider,
        service_account_file: Optional[str] = None,
    ):
        """
        Initialize the GoogleSheetsLookup.

        :param spreadsheet_url: The URL of the Google Sheet.
        :param sheet_name: The name of the specific worksheet (tab).
        :param key_column: The header name of the column to use as keys.
        :param value_column: The header name of the column to use as values.
        :param configuration_provider: The ConfigurationProvider instance.
        :param service_account_file: Optional path to the service account JSON file.
                                     If not provided, it will be looked up in the configuration.
        """
        self.spreadsheet_url = spreadsheet_url
        self.sheet_name = sheet_name
        self.key_column = key_column
        self.value_column = value_column
        self.configuration_provider = configuration_provider
        self.service_account_file = service_account_file

        self._data: Dict[str, Any] = {}
        self._load_data()

    def _resolve_service_account_file(self) -> Optional[str]:
        """
        Resolves the service account file path.
        Priority:
        1. Argument passed to __init__
        2. 'SERVICE_ACCOUNT_FILE' from ConfigurationProvider
        """
        if self.service_account_file:
            return self.service_account_file

        # Attempt to retrieve from ConfigurationProvider
        return self.configuration_provider.get_value("SERVICE_ACCOUNT_FILE")

        # Fallback: check environment variable directly if ConfigurationProvider
        # behavior is different or it didn't return anything.
        return os.getenv("SERVICE_ACCOUNT_FILE")

    def _load_data(self):
        """
        Connects to Google Sheets and preloads the data into a dictionary.
        """
        credentials_file = self._resolve_service_account_file()

        try:
            if credentials_file:
                logger.info(
                    f"Connecting to Google Sheets using credentials: {credentials_file}"
                )
                gc = gspread.service_account(filename=credentials_file)
            else:
                logger.info(
                    "Connecting to Google Sheets using default environment credentials"
                )
                gc = gspread.service_account()

            # Open spreadsheet by URL
            sh = gc.open_by_url(self.spreadsheet_url)

            # Select worksheet
            worksheet = sh.worksheet(self.sheet_name)

            # Get all records
            records = worksheet.get_all_records()
            logger.info(
                f"Fetched {len(records)} records from sheet '{self.sheet_name}'"
            )

            # Build lookup dictionary
            for i, record in enumerate(records):
                key = record.get(self.key_column)
                value = record.get(self.value_column)

                if key is None:
                    logger.warning(
                        f"Row {i + 2}: Key column '{self.key_column}' is missing or empty. Skipping."
                    )
                    continue

                # We stringify the key to ensure consistent lookup, optional but recommended for mixed types
                self._data[str(key)] = value

            logger.info(f"Successfully loaded {len(self._data)} items into cache.")

        except Exception as e:
            logger.error(f"Failed to load data from Google Sheets: {e}")
            raise

    def get_value(self, key: Any) -> Optional[Any]:
        """
        Look up a value by its key.

        :param key: The key to look up.
        :return: The corresponding value, or None if not found.
        """
        return self._data.get(str(key))

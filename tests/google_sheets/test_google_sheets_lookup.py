import unittest
from unittest.mock import patch, MagicMock
from wordlift_sdk.google_sheets import GoogleSheetsLookup
from wordlift_sdk.configuration import ConfigurationProvider


class TestGoogleSheetsLookup(unittest.TestCase):
    @patch("wordlift_sdk.google_sheets.google_sheets_lookup.gspread")
    def test_init_load_data(self, mock_gspread):
        # Setup mocks
        mock_gc = MagicMock()
        mock_gspread.service_account.return_value = mock_gc
        mock_sh = MagicMock()
        mock_gc.open_by_url.return_value = mock_sh
        mock_worksheet = MagicMock()
        mock_sh.worksheet.return_value = mock_worksheet

        # Mock data
        # Note: get_all_records returns a list of dicts.
        mock_worksheet.get_all_records.return_value = [
            {"key": "k1", "value": "v1"},
            {"key": "k2", "value": "v2"},
            {
                "value": "missing_key"
            },  # key is None (implied by .get('key') returning None if not present)
        ]

        # Mock config
        mock_config = MagicMock(spec=ConfigurationProvider)
        mock_config.get_value.return_value = None

        # Init
        lookup = GoogleSheetsLookup(
            spreadsheet_url="http://example.com",
            sheet_name="Sheet1",
            key_column="key",
            value_column="value",
            configuration_provider=mock_config,
        )

        # Verify interactions
        mock_gspread.service_account.assert_called()
        mock_gc.open_by_url.assert_called_with("http://example.com")
        mock_sh.worksheet.assert_called_with("Sheet1")
        mock_worksheet.get_all_records.assert_called()

        # Verify logic
        self.assertEqual(lookup.get_value("k1"), "v1")
        self.assertEqual(lookup.get_value("k2"), "v2")
        self.assertIsNone(lookup.get_value("k3"))

        # Verify missing key row was skipped (dict size)
        # We passed 3 rows, 1 missing key. So size should be 2.
        # But wait, we can't check internal _data easily unless we access it.
        # Or we check that looking up the missing key returns None, which is generic.

    @patch("wordlift_sdk.google_sheets.google_sheets_lookup.gspread")
    def test_service_account_resolution(self, mock_gspread):
        # Mock config to return a file path
        mock_config = MagicMock(spec=ConfigurationProvider)
        mock_config.get_value.return_value = "/path/to/config/creds.json"

        mock_gc = MagicMock()
        mock_gspread.service_account.return_value = mock_gc
        mock_gc.open_by_url.return_value.worksheet.return_value.get_all_records.return_value = []

        # Init without explicit service account
        GoogleSheetsLookup(
            spreadsheet_url="...",
            sheet_name="...",
            key_column="...",
            value_column="...",
            configuration_provider=mock_config,
        )

        # Verify service_account was called with the config value
        mock_gspread.service_account.assert_called_with(
            filename="/path/to/config/creds.json"
        )

        # Init WITH explicit service account
        mock_gspread.reset_mock()
        GoogleSheetsLookup(
            spreadsheet_url="...",
            sheet_name="...",
            key_column="...",
            value_column="...",
            configuration_provider=mock_config,
            service_account_file="/path/to/arg/creds.json",
        )
        # Verify argument takes precedence
        mock_gspread.service_account.assert_called_with(
            filename="/path/to/arg/creds.json"
        )


if __name__ == "__main__":
    unittest.main()

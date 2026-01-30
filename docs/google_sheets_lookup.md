# Google Sheets Lookup

The `GoogleSheetsLookup` class provides a high-performance, O(1) mechanism to look up values from a Google Sheet based on a key column. It preloads the data into memory upon initialization.

## Usage

```python
from wordlift_sdk.google_sheets import GoogleSheetsLookup
from wordlift_sdk.configuration import ConfigurationProvider

# 1. Create a configuration provider
config_provider = ConfigurationProvider.create()

# 2. Initialize the lookup
# Ensure you have Google Sheets credentials configured (env var or file)
lookup = GoogleSheetsLookup(
    spreadsheet_url="https://docs.google.com/spreadsheets/d/your-sheet-id",
    sheet_name="Sheet1",
    key_column="SKU",
    value_column="Price",
    configuration_provider=config_provider
)

# 3. Get values
price = lookup.get_value("12345")
if price:
    print(f"Price: {price}")
else:
    print("Item not found")
```

## Configuration

The class resolves the service account credentials in the following order:
1. `service_account_file` argument passed to `__init__`.
2. `SERVICE_ACCOUNT_FILE` value from the `ConfigurationProvider`.
3. `SERVICE_ACCOUNT_FILE` environment variable.

## API Reference

### `GoogleSheetsLookup`

**`__init__(self, spreadsheet_url: str, sheet_name: str, key_column: str, value_column: str, configuration_provider: ConfigurationProvider, service_account_file: Optional[str] = None)`**

- **spreadsheet_url**: The URL of the Google Sheet.
- **sheet_name**: The name of the specific worksheet (tab).
- **key_column**: The header name of the column to use as keys.
- **value_column**: The header name of the column to use as values.
- **configuration_provider**: The `ConfigurationProvider` instance.
- **service_account_file**: Optional path to the service account JSON file.

**`get_value(self, key: Any) -> Optional[Any]`**

- **key**: The key to look up.
- **Returns**: The corresponding value, or `None` if not found.

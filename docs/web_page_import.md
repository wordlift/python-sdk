# Web Page Import

The `WebPageImportUrlHandler` is responsible for sending URLs to the WordLift API for import. It supports various configuration options to control how web pages are fetched and processed.

## Configuration

The behavior of the web page import can be customized using the following configuration keys. These can be set in your `config/default.py`, environment variables, or passed via the `ConfigurationProvider`.

### General Options

*   **`WEB_PAGE_IMPORT_WRITE_STRATEGY`** (default: `createOrUpdateModel`):
    *   `createOrUpdateModel`: Replaces existing entities in the Knowledge Graph.
    *   `patchReplaceModel`: Replaces only specific properties (`type`, `headline`, `abstract`, `text`).
*   **`WEB_PAGE_TYPES`** (default: `["http://schema.org/Article"]`): A list of Schema.org types to assign to the imported entities.
*   **`EMBEDDING_PROPERTIES`** (default: `["http://schema.org/headline", "http://schema.org/abstract", "http://schema.org/text"]`): A list of properties to generate embeddings for.

### Fetch Options

The following options control how the WordLift scraper fetches the content from the target URLs.

*   **`WEB_PAGE_IMPORT_MODE`** (default: `default`):
    *   `default`: Smart fallback strategy.
    *   `proxy`: Uses a proxy to fetch the page.
    *   `premium_scraper`: Uses a premium scraper (required for advanced options like JS rendering).
*   **`WEB_PAGE_IMPORT_RENDER_JS`** (bool, optional):
    *   Set to `True` to enable JavaScript rendering. Requires `WEB_PAGE_IMPORT_MODE` to be `premium_scraper`.
*   **`WEB_PAGE_IMPORT_WAIT_FOR`** (str, optional):
    *   A CSS selector to wait for before capturing the page content. Useful for pages that load content dynamically. Requires `WEB_PAGE_IMPORT_MODE` to be `premium_scraper`.
*   **`WEB_PAGE_IMPORT_COUNTRY_CODE`** (str, optional):
    *   The 2-letter country code (ISO 3166-1 alpha-2) for the proxy location. Requires `WEB_PAGE_IMPORT_MODE` to be `premium_scraper`.
*   **`WEB_PAGE_IMPORT_PREMIUM_PROXY`** (bool, optional):
    *   Set to `True` to use premium residential proxies. Requires `WEB_PAGE_IMPORT_MODE` to be `premium_scraper`.
*   **`WEB_PAGE_IMPORT_BLOCK_ADS`** (bool, optional):
    *   Set to `True` to block ads during scraping to save bandwidth and improve speed. Requires `WEB_PAGE_IMPORT_MODE` to be `premium_scraper`.
*   **`WEB_PAGE_IMPORT_TIMEOUT`** (int, optional):
    *   The timeout in milliseconds for the fetch operation.

## Usage Example

To configure the SDK to use the premium scraper with JavaScript rendering and wait for a specific element:

**`config/default.py`**

```python
WEB_PAGE_IMPORT_MODE = "premium_scraper"
WEB_PAGE_IMPORT_RENDER_JS = True
WEB_PAGE_IMPORT_WAIT_FOR = "#content"
WEB_PAGE_IMPORT_BLOCK_ADS = True
```

## API Reference

### `WebPageImportUrlHandler`

**`__init__(self, context: Context, embedding_properties: list[str], web_page_types: list[str], web_page_import_callback: WebPageImportProtocolInterface | None = None, write_strategy: str = "createOrUpdateModel", fetch_options: WebPageImportFetchOptions | None = None)`**

*   **`context`**: The application context.
*   **`embedding_properties`**: List of properties for embeddings.
*   **`web_page_types`**: List of RDF types for the imported entity.
*   **`web_page_import_callback`**: Optional callback interface for handling the import response.
*   **`write_strategy`**: The write strategy (`createOrUpdateModel` or `patchReplaceModel`).
*   **`fetch_options`**: Optional `WebPageImportFetchOptions` object containing advanced fetch settings.

## Retry Behavior

Import/scrape/search-console URL handlers and protocol queues include retries for transport errors and WordLift service errors.
For Pydantic validation failures, retries use `pydantic_core.ValidationError` from the public API path for Python 3.14 compatibility.

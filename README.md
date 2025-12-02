 # WordLift Python SDK

A Python toolkit for orchestrating WordLift imports: fetch URLs from sitemaps, Google Sheets, or explicit lists, filter out already imported pages, enqueue search console jobs, push RDF graphs, and call the WordLift APIs to import web pages.

## Features
- URL sources: XML sitemaps (with optional regex filtering), Google Sheets (`url` column), or Python lists.
- Change detection: skips URLs that are already imported unless `OVERWRITE` is enabled; re-imports when `lastmod` is newer.
- Web page imports: sends URLs to WordLift with embedding requests, output types, retry logic, and pluggable callbacks.
- Search Console refresh: triggers analytics imports when top queries are stale.
- Graph templates: renders `.ttl.liquid` templates under `data/templates` with account data and uploads the resulting RDF graphs.
- Extensible: override protocols via `WORDLIFT_OVERRIDE_DIR` without changing the library code.

## Installation

```bash
pip install wordlift-sdk
# or
poetry add wordlift-sdk
```

Requires Python 3.10–3.13.

## Configuration

Settings are read in order: `config/default.py` (or a custom path you pass to `ConfigurationProvider.create`), environment variables, then (when available) Google Colab `userdata`.

Common options:
- `WORDLIFT_KEY` (required): WordLift API key.
- `API_URL`: WordLift API base URL, defaults to `https://api.wordlift.io`.
- `SITEMAP_URL`: XML sitemap to crawl; `SITEMAP_URL_PATTERN` optional regex to filter URLs.
- `SHEETS_URL`, `SHEETS_NAME`, `SHEETS_SERVICE_ACCOUNT`: use a Google Sheet as source; service account points to credentials file.
- `URLS`: list of URLs (e.g., `["https://example.com/a", "https://example.com/b"]`).
- `OVERWRITE`: re-import URLs even if already present (default `False`).
- `WEB_PAGE_IMPORT_WRITE_STRATEGY`: WordLift write strategy (default `createOrUpdateModel`).
- `EMBEDDING_PROPERTIES`: list of schema properties to embed.
- `WEB_PAGE_TYPES`: output schema types, defaults to `["http://schema.org/Article"]`.
- `GOOGLE_SEARCH_CONSOLE`: enable/disable Search Console handler (default `True`).
- `CONCURRENCY`: max concurrent handlers, defaults to `min(cpu_count(), 4)`.
- `WORDLIFT_OVERRIDE_DIR`: folder containing protocol overrides (default `app/overrides`).

Example `config/default.py`:

```python
WORDLIFT_KEY = "your-api-key"
SITEMAP_URL = "https://example.com/sitemap.xml"
SITEMAP_URL_PATTERN = r"^https://example.com/article/.*$"
GOOGLE_SEARCH_CONSOLE = True
WEB_PAGE_TYPES = ["http://schema.org/Article"]
EMBEDDING_PROPERTIES = [
    "http://schema.org/headline",
    "http://schema.org/abstract",
    "http://schema.org/text",
]
```

## Running the import workflow

```python
import asyncio
from wordlift_sdk import run_kg_import_workflow

if __name__ == "__main__":
    asyncio.run(run_kg_import_workflow())
```

The workflow:
1. Renders and uploads RDF graphs from `data/templates/*.ttl.liquid` using account info.
2. Builds the configured URL source and filters out unchanged URLs (unless `OVERWRITE`).
3. Sends each URL to WordLift for import with retries and optional Search Console refresh.

You can build components yourself when you need more control:

```python
import asyncio
from wordlift_sdk.container.application_container import ApplicationContainer

async def main():
    container = ApplicationContainer()
    workflow = await container.create_kg_import_workflow()
    await workflow.run()

asyncio.run(main())
```

## Custom callbacks and overrides

Override the web page import callback by placing `web_page_import_protocol.py` with a `WebPageImportProtocol` class under `WORDLIFT_OVERRIDE_DIR` (default `app/overrides`). The callback receives a `WebPageImportResponse` and can push to `graph_queue` or `entity_patch_queue`.

## Templates

Add `.ttl.liquid` files under `data/templates`. Templates render with `account` fields available (e.g., `{{ account.dataset_uri }}`) and are uploaded before URL handling begins.

## Testing

```bash
poetry install --with dev
poetry run pytest
```

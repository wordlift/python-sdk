# Ingestion Pipeline

Introduced in SDK `5.0.0`.

## Overview

The SDK now exposes a reusable two-axis ingestion model:

- Axis A (source): where items come from.
- Axis B (loader): how each item is fetched/resolved.

Pipeline shape:

`SourceAdapter -> SourceItem -> LoaderAdapter -> LoadedPage`

The orchestrator resolves adapters via registries and emits uniform events.

## Public Contracts

### SourceAdapter

- `iter_items(config) -> Iterator[SourceItem]`

### LoaderAdapter

- `load(item, config) -> LoadedPage`

### Models

- `SourceItem`
  - `id: str`
  - `url: str`
  - `metadata: dict[str, Any]`
  - `html: str | None`
- `LoadedPage`
  - `item_id: str`
  - `url: str`
  - `final_url: str | None`
  - `status_code: int | None`
  - `html: str`
  - `fetch_meta: dict[str, Any]`

## Configuration Schema

### New Global Keys

- `INGEST_SOURCE`: `urls|sitemap|sheets|local` (required)
- `INGEST_LOADER`: `simple|proxy|playwright|premium_scraper|web_scrape_api|passthrough` (required)
- `INGEST_PASSTHROUGH_WHEN_HTML`: bool (default `true`)
- `INGEST_TIMEOUT_MS`: int milliseconds (default `30000`)
- `INGEST_RETRY_ATTEMPTS`: int (default `5`)
- `INGEST_RETRY_BACKOFF_MS`: int milliseconds (default `2000`)
- `URL_REGEX`: optional regex applied to all source URLs before loader execution
  and in the graph-sync URL-source bridge before `new_or_changed` GraphQL lookup

### Precedence

1. `INGEST_SOURCE` and `INGEST_LOADER` are explicit and required.
2. Legacy resolver fallback (`WEB_PAGE_IMPORT_MODE`, `WEB_PAGE_IMPORT_TIMEOUT`, implicit source auto-priority) is removed.
- Passthrough shortcut: if item has embedded HTML and `INGEST_PASSTHROUGH_WHEN_HTML=true`, effective loader is `passthrough`.
- `SITEMAP_URL_PATTERN` is deprecated and treated as a sitemap-only alias for `URL_REGEX`.

Source alias compatibility:

- `local <-> debug-cloud` accepted.

## Loader Semantics

### `web_scrape_api`

Managed API loader mode. SDK treats it as a single loader mode and does not add SDK-level fallback knobs.

`LoadedPage.fetch_meta` includes:

- `backend=web_scrape_api`
- `request_id` (if available)
- `provider_status` / `provider_details` (if available)

### Sitemap source request headers

Sitemap discovery (`INGEST_SOURCE=sitemap`) uses `advertools` with an explicit
browser-like header bundle aligned to Playwright/browser defaults (`User-Agent`,
`Accept`, `Accept-Language`, `Referer`, `Upgrade-Insecure-Requests`, and
`Sec-CH-*` client hints) so sitemap fetch identity is closer to page-rendering
requests.

### `playwright`

If Playwright is unavailable, loader raises typed error `INGEST_LOAD_PLAYWRIGHT_UNAVAILABLE`.
When ingestion runs from an active asyncio workflow, Playwright rendering is isolated from the
event-loop thread so Sync API calls are not executed directly inside the running loop.
Default Playwright wait policy is `domcontentloaded`. On navigation timeout, ingestion now
falls back to returning the current page DOM snapshot instead of failing immediately.
For browser/runtime failures, loader preserves compatibility (`code=INGEST_LOAD_BROWSER_ERROR`,
message `Playwright loader failed for <url>`) and includes structured root-cause details in
`ingest.item_failed.meta`:

- `root_exception_type`
- `root_exception_message` (truncated to 2KB)
- `phase` (`launch|navigate|content|convert|unknown`)
- `url`
- `wait_until`
- `timeout_ms`
- `headless`

## Events

Orchestrator emits structured events:

- `ingest.warning`
- `ingest.item_started`
- `ingest.item_loaded`
- `ingest.item_failed`
- `ingest.summary`

Failure payloads include machine-parseable `code` and `retryable`.
When the ingestion bridge URL handler raises on loader failure, it appends a parseable
`diagnostics=<json>` suffix (when failure meta exists) with sanitized/truncated
`ingest.item_failed.meta` fields.
For `kg_build` ingestion bridge execution, callback emission is skipped when
`LoadedPage.status_code >= 400` (for example HTTP 404/500). The handler raises
for that URL so downstream graph/import callback processing does not run on
error-status pages.

## Quick Usage

```python
from wordlift_sdk.ingestion import run_ingestion

result = run_ingestion(
    {
        "INGEST_SOURCE": "urls",
        "URLS": ["https://example.com/a"],
        "INGEST_LOADER": "web_scrape_api",
        "URL_REGEX": r"^https://example.com/",
        "WORDLIFT_KEY": "...",
    }
)

for page in result.pages:
    print(page.url, page.status_code)
```

## Implementation Note

### New Public SDK APIs

- `wordlift_sdk.ingestion.SourceAdapter`
- `wordlift_sdk.ingestion.LoaderAdapter`
- `wordlift_sdk.ingestion.SourceItem`
- `wordlift_sdk.ingestion.LoadedPage`
- `wordlift_sdk.ingestion.ResolvedIngestionConfig`
- `wordlift_sdk.ingestion.create_source_registry()`
- `wordlift_sdk.ingestion.create_loader_registry()`
- `wordlift_sdk.ingestion.IngestionOrchestrator`
- `wordlift_sdk.ingestion.run_ingestion(...)`
- `wordlift_sdk.ingestion.create_type_classification_csv_from_ingestion(...)`

### Deprecated/Internal APIs

Legacy resolver compatibility mapping from `WEB_PAGE_IMPORT_*` to `INGEST_*` is removed.

### Compatibility Table (Exact)

| Mode name | Resolved loader |
| --- | --- |
| `default` | `web_scrape_api` |
| `proxy` | `proxy` |
| `premium_scraper` | `premium_scraper` |
| `simple` | `simple` |
| `playwright` | `playwright` |
| `web_scrape_api` | `web_scrape_api` |
| `passthrough` | `passthrough` |

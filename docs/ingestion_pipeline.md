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

- `INGEST_SOURCE`: `auto|urls|sitemap|sheets|local`
- `INGEST_LOADER`: `auto|simple|proxy|playwright|premium_scraper|web_scrape_api|passthrough`
- `INGEST_PASSTHROUGH_WHEN_HTML`: bool (default `true`)
- `INGEST_TIMEOUT_MS`: int milliseconds (default `30000`)
- `INGEST_RETRY_ATTEMPTS`: int (default `5`)
- `INGEST_RETRY_BACKOFF_MS`: int milliseconds (default `2000`)

### Precedence

1. If `INGEST_*` is set, it wins over legacy keys.
2. If `INGEST_*` is unset, resolve from legacy keys.
3. If both new+legacy disagree, use `INGEST_*` and emit `INGEST_CFG_CONFLICT` warning with parseable payload.

### Auto Resolution

- Source priority: `URLS > SITEMAP_URL > SHEETS_* > local`
- Loader auto: `web_scrape_api`
- Passthrough shortcut: if item has embedded HTML and `INGEST_PASSTHROUGH_WHEN_HTML=true`, effective loader is `passthrough`.

### Legacy Compatibility Mapping

| Legacy `WEB_PAGE_IMPORT_MODE` | Canonical loader |
| --- | --- |
| `default` | `web_scrape_api` |
| `proxy` | `proxy` |
| `premium_scraper` | `premium_scraper` |

Source alias compatibility:

- `local <-> debug-cloud` accepted.

## Loader Semantics

### `web_scrape_api`

Managed API loader mode. SDK treats it as a single loader mode and does not add SDK-level fallback knobs.

`LoadedPage.fetch_meta` includes:

- `backend=web_scrape_api`
- `request_id` (if available)
- `provider_status` / `provider_details` (if available)

### `playwright`

If Playwright is unavailable, loader raises typed error `INGEST_LOAD_PLAYWRIGHT_UNAVAILABLE`.

## Events

Orchestrator emits structured events:

- `ingest.warning`
- `ingest.item_started`
- `ingest.item_loaded`
- `ingest.item_failed`
- `ingest.summary`

Failure payloads include machine-parseable `code` and `retryable`.

## Quick Usage

```python
from wordlift_sdk.ingestion import run_ingestion

result = run_ingestion(
    {
        "INGEST_SOURCE": "urls",
        "URLS": ["https://example.com/a"],
        "INGEST_LOADER": "web_scrape_api",
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

### Deprecated/Internal APIs

No hard removals in this change.

Legacy URL ingestion internals remain for compatibility and are now considered compatibility-layer surfaces:

- `wordlift_sdk.url_source.*`
- `wordlift_sdk.workflow.url_handler.*`

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

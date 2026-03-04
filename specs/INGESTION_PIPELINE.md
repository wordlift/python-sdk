# Ingestion Pipeline Spec

## Purpose

Provide a reusable, SDK-level ingestion architecture with two independent axes:

- Source axis: item discovery.
- Loader axis: item retrieval.

## Contracts

- `SourceAdapter.iter_items(config) -> Iterator[SourceItem]`
- `LoaderAdapter.load(item, config) -> LoadedPage`

Shared models:

- `SourceItem(id, url, metadata, html=None)`
- `LoadedPage(item_id, url, final_url, status_code, html, fetch_meta)`

## Registries

The SDK uses registry-based resolution for both axes.

- Source registry keys: `urls`, `sitemap`, `sheets`, `local`
- Loader registry keys: `simple`, `proxy`, `playwright`, `premium_scraper`, `web_scrape_api`, `passthrough`

Alias support:

- Source: `debug-cloud` resolves to `local`.

## Resolver Behavior

### New Keys

- `INGEST_SOURCE`
- `INGEST_LOADER`
- `INGEST_PASSTHROUGH_WHEN_HTML`
- `INGEST_TIMEOUT_MS`
- `INGEST_RETRY_ATTEMPTS`
- `INGEST_RETRY_BACKOFF_MS`
- `URL_REGEX`

### Deterministic Rules

- `INGEST_SOURCE` is required and must be one of `urls|sitemap|sheets|local`.
- `INGEST_LOADER` is required and must be one of `simple|proxy|playwright|premium_scraper|web_scrape_api|passthrough`.
- Legacy resolver fallback from `WEB_PAGE_IMPORT_*` and implicit source auto-priority is not supported.
- Source-specific required fields are validated strictly (`URLS`, `SITEMAP_URL`, or full `SHEETS_*` tuple, depending on `INGEST_SOURCE`).
- `URL_REGEX` is validated at resolve time and applied uniformly before loader execution.
- Graph-sync URL-source bridging (`AdapterUrlSource` -> `NewOrChangedUrlSource`)
  must also enforce resolved `url_regex` before GraphQL `new_or_changed` lookup,
  so out-of-scope URLs are excluded before change detection/import.
- `SITEMAP_URL_PATTERN` is deprecated; for `INGEST_SOURCE=sitemap` it is accepted as an alias when `URL_REGEX` is unset.

## Passthrough Precedence

If item includes embedded HTML and `INGEST_PASSTHROUGH_WHEN_HTML=true`, orchestrator must use `passthrough` before network loaders.

## Validation and Error Policy

- Fail fast on incomplete source config.
- Fail fast on unsupported loader/source names.
- Fail fast on invalid option combinations (premium-only options without `premium_scraper`).
- No secret logging in warnings/events.
- Playwright loader must keep error compatibility (`INGEST_LOAD_BROWSER_ERROR` + `Playwright loader failed for <url>`)
  while attaching structured diagnostics in `LoaderRuntimeError.details`/`ingest.item_failed.meta`:
  - `root_exception_type`
  - `root_exception_message` (max 2KB)
  - `phase` (`launch|navigate|content|convert|unknown`)
  - `url`, `wait_until`, `timeout_ms`, `headless`
- Playwright loader execution must be async-loop-safe: when called while an event loop is already
  running in the caller thread, rendering is offloaded away from that loop thread before invoking
  Sync Playwright APIs.
- Playwright default wait policy is `domcontentloaded`; explicit `PLAYWRIGHT_WAIT_UNTIL` still overrides.
- On Playwright navigation timeout, loader should continue with available page DOM content instead of
  failing immediately, and only raise browser errors for non-timeout navigation failures.
- `INGEST_LOAD_PLAYWRIGHT_UNAVAILABLE` remains reserved for missing Playwright install/runtime availability.

## Retry/Timeout Policy

Shared loader policy:

- timeout is normalized in milliseconds (`timeout_ms`)
- retries = `retry_attempts`
- fixed backoff = `retry_backoff_ms`

## Observability

Machine-parseable events:

- `ingest.warning`
- `ingest.item_started`
- `ingest.item_loaded`
- `ingest.item_failed`
- `ingest.summary`

`ingest.warning` conflict payload includes:
- `code`
- `message`
- `meta`

Bridge-handler failure surfacing contract:
- `IngestionWebPageScrapeUrlHandler` keeps base failure text
  (`Ingestion loader failed for <url>: <code> <message>`) and appends
  `diagnostics=<json>` when `ingest.item_failed.meta` includes diagnostic fields.
- Appended diagnostics are key-whitelisted, JSON-serialized with stable keys, and
  truncated/sanitized for safe logs (`root_exception_message` capped; payload capped).
- In `kg_build` bridge execution, when ingestion returns a `LoadedPage` with
  `status_code >= 400`, the handler must raise and skip callback emission for
  that URL to prevent graph/import processing on HTTP error pages.

## Sitemap Fetch Identity

- `SitemapSourceAdapter` must call `advertools.sitemaps.sitemap_to_df` with
  browser-like `request_headers` built from Playwright defaults (`User-Agent`,
  `Accept`, `Accept-Language`, `Referer`, `Upgrade-Insecure-Requests`,
  `Sec-CH-UA`, `Sec-CH-UA-Mobile`, `Sec-CH-UA-Platform`).
- The configured loader (`INGEST_LOADER`) is still applied per discovered URL
  by the orchestrator; sitemap fetch headers only affect source discovery.

## web_scrape_api Semantics

`web_scrape_api` is a managed API loader mode.

`LoadedPage.fetch_meta` must include:

- `backend=web_scrape_api`
- `request_id` (if present)
- `provider_status`/`provider_details` (if present)

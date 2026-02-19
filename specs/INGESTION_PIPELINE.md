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

### Deterministic Rules

- `INGEST_*` overrides legacy keys.
- If `INGEST_*` is unset, resolver uses legacy keys.
- On disagreement, winner is `INGEST_*` and warning code `INGEST_CFG_CONFLICT` is emitted.
- Source auto priority: `URLS > SITEMAP_URL > SHEETS_* > local`.
- Loader auto resolves to `web_scrape_api`.
- Default loader is `web_scrape_api` when neither new nor legacy loader is set.

### Legacy Mode Mapping

- `default -> web_scrape_api`
- `proxy -> proxy`
- `premium_scraper -> premium_scraper`

## Passthrough Precedence

If item includes embedded HTML and `INGEST_PASSTHROUGH_WHEN_HTML=true`, orchestrator must use `passthrough` before network loaders.

## Validation and Error Policy

- Fail fast on incomplete source config.
- Fail fast on unsupported loader/source names.
- Fail fast on invalid option combinations (premium-only options without `premium_scraper`).
- No secret logging in warnings/events.

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

- `new_key`
- `new_value`
- `legacy_key`
- `legacy_value`
- `winner`

## web_scrape_api Semantics

`web_scrape_api` is a managed API loader mode.

`LoadedPage.fetch_meta` must include:

- `backend=web_scrape_api`
- `request_id` (if present)
- `provider_status`/`provider_details` (if present)

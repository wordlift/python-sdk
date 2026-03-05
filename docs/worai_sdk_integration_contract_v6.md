# Worai SDK Integration Contract v6

## Scope

This contract defines required integration behavior for worai when using
`wordlift-sdk` `6.x`.

Canonical entry point:

- `wordlift_sdk.kg_build.cloud_flow.run_cloud_workflow`

No alternate orchestration path is in scope for worai integration.

Exception for source-only inventory use cases:

- `wordlift_sdk.ingestion.resolve_ingestion_source_items(...)` is the canonical
  SDK API for URL discovery-only commands (for example
  `worai structured-data inventory`) that do not run loaders/materialization.
- `wordlift_sdk.ingestion.create_structured_data_inventory_from_ingestion(...)`
  is the canonical SDK API when worai inventory needs full inventory row
  generation (URL + FAQ flags + types + merged JSON-LD) over shared ingestion.

## Required Runtime Contract

### 1) Source Mode (exactly one per run)

Configure one and only one source mode in `CloudWorkflowConfig`:

- `urls`
- `sitemap_url` (+ optional `sitemap_url_pattern`)
- `sheets_url` + `sheets_name` + `sheets_service_account_json`

### 2) Loader Mode (explicit)

Set loader explicitly:

- `CloudWorkflowConfig.ingest_loader`

Optional timeout:

- `CloudWorkflowConfig.ingest_timeout_ms`

Legacy resolver fallback keys are removed and must not be used for integration:

- `WEB_PAGE_IMPORT_MODE`
- `WEB_PAGE_IMPORT_TIMEOUT`

### 3) Callback Contract

Supported callbacks:

- `on_info(str)`
- `on_progress(dict)`
- `on_kpi(dict)`

These callbacks are supported concurrently in the same run.

### 4) Validation Contract

- `shacl_validate_mode = off`: `validation = null`
- `shacl_validate_mode = warn`: include validation, continue
- `shacl_validate_mode = fail`: emit failing progress payload, then raise/stop failing graph path

### 5) Postprocessor Runtime Contract

Runtime precedence:

1. `profiles.<name>.postprocessor_runtime`
2. `profiles._base.postprocessor_runtime`
3. SDK default: `persistent`

## Conformance Matrix (CI Required)

For each source in:

- `urls`, `sitemap`, `sheets`

and each loader in:

- `simple`, `proxy`, `playwright`, `premium_scraper`, `web_scrape_api`, `passthrough`

verify:

1. resolver accepts explicit `INGEST_SOURCE` + `INGEST_LOADER`
2. source-specific required fields are enforced
3. unsupported source/loader fails fast
4. canonical cloud flow emits expected source keys and callbacks
5. source-only inventory path reuses ingestion resolver/source adapters via
   `resolve_ingestion_source_items(...)` (no local duplicated sitemap resolver)

Reference test suites:

- `tests/ingestion/test_resolver_matrix.py`
- `tests/kg_build/test_cloud_flow.py`
- `tests/kg_build/test_protocol.py`

## Packaging + Distribution

This document is shipped with SDK package artifacts and is version-locked to
the published SDK version.

PyPI consumers should use the docs bundled with installed artifacts and verify
breaking changes against `CHANGELOG.md`.

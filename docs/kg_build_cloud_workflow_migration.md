# KG Build Canonical Cloud Workflow Migration

## Effective Version

- Breaking release: `6.0.0` (February 24, 2026)
- Canonical path: `wordlift_sdk.kg_build.cloud_flow.run_cloud_workflow`

## What Changed

1. Worai integration must use `run_cloud_workflow` as the single supported orchestration path.
2. `run_cloud_workflow` source selection requires exactly one source mode per run:
   - `urls`
   - `sitemap_url` (optional `sitemap_url_pattern`)
   - `sheets_url` + `sheets_name`
3. Default postprocessor runtime is now `persistent`.
4. Legacy loader fallback keys are removed from the shared ingestion resolver:
   - `WEB_PAGE_IMPORT_MODE`
   - `WEB_PAGE_IMPORT_TIMEOUT`
   Use explicit `INGEST_LOADER`, `INGEST_TIMEOUT_MS`, and `PLAYWRIGHT_WAIT_UNTIL`.
   `run_cloud_workflow` still accepts legacy timeout compatibility input via
   `extra_settings["WEB_PAGE_IMPORT_TIMEOUT"]` only when
   `CloudWorkflowConfig.ingest_timeout_ms` is unset.

## Source Mode Mapping

- URL list mode:
  - set `CloudWorkflowConfig.urls`
- Sitemap mode:
  - set `CloudWorkflowConfig.sitemap_url`
  - optional `CloudWorkflowConfig.sitemap_url_pattern`
- Sheets mode:
  - set `CloudWorkflowConfig.sheets_url`
  - set `CloudWorkflowConfig.sheets_name`
  - set `CloudWorkflowConfig.sheets_service_account_json`

Do not configure multiple source modes in the same `CloudWorkflowConfig`.

## Loader Mapping

- Configure `CloudWorkflowConfig.ingest_loader` explicitly.
- Optional timeout control: `CloudWorkflowConfig.ingest_timeout_ms`.
- Optional Playwright wait strategy control:
  `CloudWorkflowConfig.playwright_wait_until`.

## Callback Contract

`run_cloud_workflow` continues to support:

- `on_info(str)`
- `on_progress(dict)`
- `on_kpi(dict)`

These callbacks can be used together in a single run.

## Validation Semantics

- `shacl_validate_mode = off`: progress `validation` is `null`, final KPI `validation` is `null`.
- `shacl_validate_mode = warn`: include validation payloads and continue.
- `shacl_validate_mode = fail`: emit failing progress payload, then raise and stop the failing graph/static-template sync path.

## Failed URL Tolerance

`run_cloud_workflow` raises `SystemExit("Total URLs: N, Successes: S, Failures: F")`
when the run has failed URLs, and logs each failed URL with its error. Two
optional settings let a large run tolerate a few failures; they are read from
`extra_settings`, where worai puts unknown `worai.toml` keys (upper-cased):

- `MAX_FAILED_URLS`: int, default `0`.
- `MAX_FAILED_URLS_RATIO`: float in `[0, 1]`, default `0`; compared with
  `failed URLs / distinct URLs` (a URL listed twice counts once).

Failures are counted per distinct URL (a URL that fails in two handlers counts
once). The run fails only when the failed URLs exceed both limits. With the
defaults (both `0`) any failure fails the run, as before. A tolerated run logs
a warning with the summary, the limits and the failed URLs, and returns
normally, so a following KPI step still runs. Invalid or out-of-range values
raise `CloudWorkflowConfigError` before the workflow starts.

Example (`worai.toml` profile):

```toml
max_failed_urls_ratio = 0.005  # tolerate up to 0.5% failed URLs
```

## Runtime Semantics

`postprocessor_runtime` precedence remains:

1. `profiles.<name>.postprocessor_runtime`
2. `profiles._base.postprocessor_runtime`
3. SDK default: `persistent`

## Deprecation Window

- Deprecated: `6.0.0` on February 24, 2026.
- Removal target: `7.0.0` on or before June 30, 2026.

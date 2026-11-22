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

## Runtime Semantics

`postprocessor_runtime` precedence remains:

1. `profiles.<name>.postprocessor_runtime`
2. `profiles._base.postprocessor_runtime`
3. SDK default: `persistent`

## Deprecation Window

- Deprecated: `6.0.0` on February 24, 2026.
- Removal target: `7.0.0` on or before June 30, 2026.

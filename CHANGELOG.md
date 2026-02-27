# Changelog

## 6.6.1 - 2026-02-27

### Changed

- Regenerate `poetry.lock` after adding `trafilatura` so CI and tag-based PyPI
  publish workflows install from an up-to-date lock file.

## 6.6.0 - 2026-02-27

### Added

- Add shared local agent CLI module:
  - `wordlift_sdk.agent_cli.LocalAgentCliRunner`
  - non-interactive local CLI execution for `claude|codex|gemini`
  - auto-selection order when unspecified: `claude` -> `codex` -> `gemini`.
- Add ingestion-backed type classification export API:
  - `wordlift_sdk.ingestion.create_type_classification_csv_from_ingestion(...)`
  - output columns: `url,main_type,additional_types,explanation`
  - markdown body extraction via `trafilatura`.

### Changed

- Add global ingestion URL filtering via `URL_REGEX` across all ingestion
  sources (`urls|sitemap|sheets|local`) before loader execution.
- Deprecate `SITEMAP_URL_PATTERN`; for sitemap sources it is now treated as an
  alias of `URL_REGEX` when `URL_REGEX` is unset.
- Documentation/spec indices and ingestion pipeline docs updated for the new
  URL filter contract and local agent classification workflow.

## 6.5.0 - 2026-02-26

### Added

- Add reusable Google Search Console canonical-selection API:
  - `create_canonical_csv_from_gsc_impressions(...)`
  - interval parsing helper `parse_interval_to_date_range("XX[d|w|m]")`
  - credential loaders for service-account and authorized-user OAuth token files.
- Add shared adaptive concurrency controller:
  - `wordlift_sdk.utils.auto_concurrency.AutoConcurrencyController`
- Add internal/client implementation specs for GSC canonical selection:
  - `specs/GSC_CANONICAL_SELECTION.md`
  - `specs/INDEX.md`

### Changed

- `structured_data.batch` now reuses shared adaptive concurrency policy from
  `wordlift_sdk.utils.auto_concurrency`.
- GSC canonical selection uses `concurrency="N|auto"` as the public concurrency
  input.
- Documentation/status sync for new GSC canonical API and specs index.

## 6.3.0 - 2026-02-25

### Added

- `kg_build` existing-entity URL lookup now loads `seovoc:importHash` and propagates it through URL handlers into protocol callback processing.
- Added `import_hash_mode` / `IMPORT_HASH_MODE` runtime control for graph patching (`on|write|off`).

### Changed

- `kg_build` per-node import hash computation is sibling-aware within the dataset graph snapshot and continues excluding `seovoc:importHash` from hash input.
- `kg_build` source annotation now targets first-level dataset IDs (`/<dataset>/<bucket>/<id>`) for `seovoc:source = "web-page-import"` instead of annotating all URI subjects.

## 6.2.0 - 2026-02-25

### Breaking

- `kg_build` validation toggle `shacl_validate_sync` / `SHACL_VALIDATE_SYNC` is removed; validation behavior is now controlled only by `shacl_validate_mode`.
- `kg_build` validation mode value `strict` is replaced by `fail` (`off|warn|fail`).
- `kg_build` setting `shacl_shape_specs` / `SHACL_SHAPE_SPECS` is removed in favor of resolver-aligned shape inputs (`shacl_builtin_shapes`, `shacl_exclude_builtin_shapes`, `shacl_extra_shapes`).

### Changed

- `kg_build` SHACL validation now resolves shape specs via `resolve_shape_specs(...)` using bundled include/exclude lists plus local/remote overlays.
- `kg_build` progress/KPI callback payload schema remains unchanged; only validation mode/settings semantics were updated.

## 6.1.0 - 2026-02-25

### Added

- Add SDK-level validation shape composition helper `resolve_shape_specs(...)` to support bundled-shape allowlist/denylist plus extra local/remote SHACL overlays without duplicating validator logic in host tools.
- Add structured SHACL issue helpers (`ValidationIssue`, `extract_validation_issues`, `filter_validation_issues`) with stable `rule_id`/`rule_set` fields for host-side UX/CLI layers.

### Changed

- Extend SHACL shape loading to accept additional remote shape URLs in addition to local files and bundled resources.
- Document validation composition and issue-filtering as API-first SDK contracts (`README`, `docs/validation.md`, `specs/validation.md`, and index/status docs).

## 6.0.6 - 2026-02-25

### Changed

- Fix Playwright ingestion failures in async workflow by avoiding Sync API execution inside active asyncio loops; preserve detailed ingestion diagnostics.
- Update `IngestionWebPageScrapeUrlHandler` error surfacing to append parseable, truncated diagnostics from `ingest.item_failed.meta` (phase, root cause type/message, url, wait policy, timeout, headless) while preserving existing code/message text.
- Playwright ingestion default navigation wait policy is now `domcontentloaded` (was `networkidle`) to reduce timeout failures on long-polling pages.
- Playwright browser navigation timeouts now fall back to returning partial page content (`page.content()`) instead of failing ingestion immediately.
- `HtmlConverter` now strips default XHTML `xmlns` declarations from converted output so unprefixed XPath selectors (for example `.//div`, `.//h1`, `.//title`) work against `__XHTML__` sources.
- `kg_build` static template bootstrap is now concurrency-safe in cloud runs: static templates are patched once per run and `on_progress` emits a single `kind=static_templates` startup payload.
- `kg_build` debug-cloud callback artifacts now also persist source HTML/XHTML snapshots per URL (`<sha256(url)>.html/.xhtml`) in addition to graph Turtle files.

## 6.0.1 - 2026-02-24

### Changed

- Improve Playwright ingestion diagnostics by surfacing root cause details in ingest.item_failed.meta while preserving existing error codes/messages.

## 6.0.0 - 2026-02-24

### Breaking

- Canonical worai execution path is now `wordlift_sdk.kg_build.cloud_flow.run_cloud_workflow` only.
- `run_cloud_workflow` source selection now requires exactly one explicit source mode:
  - `urls`
  - `sitemap_url` (optional `sitemap_url_pattern`)
  - `sheets_url` + `sheets_name`
- SDK default postprocessor runtime is now `persistent` (previously `oneshot`).
- Legacy ingestion resolver fallback naming is removed:
  - no fallback from `WEB_PAGE_IMPORT_MODE` to loader
  - no fallback from `WEB_PAGE_IMPORT_TIMEOUT` to timeout
  - `INGEST_SOURCE` and `INGEST_LOADER` are now required for ingestion resolution.

### Added

- Canonical-path conformance coverage for `run_cloud_workflow` across `urls`, `sitemap_url` (+ pattern), and `sheets` source modes.
- Source/loader matrix conformance tests across `INGEST_SOURCE` (`urls|sitemap|sheets`) and loader set (`simple|proxy|playwright|premium_scraper|web_scrape_api|passthrough`).
- Added `docs/worai_sdk_integration_contract_v6.md` and packaged docs/changelog artifacts for version-locked SDK distribution via PyPI.

### Deprecation Window

- Legacy non-canonical orchestration behavior is deprecated as of `6.0.0` on February 24, 2026.
- Final removal window closes with `7.0.0` on or before June 30, 2026.

### Migration

- See `docs/kg_build_cloud_workflow_migration.md` for migration steps to canonical `run_cloud_workflow`.

## 5.4.1 - 2026-02-24

### Changed

- `kg_build` strict SHACL mode now emits failing `on_progress` payloads before raising, so graph/static-template failure context is available in telemetry while still stopping the strict sync path.
- Final `on_kpi` payload now uses `validation: null` when SHACL sync validation is disabled.

### Compatibility

- Legacy `on_info` callback support is unchanged and coexists with `on_progress` and `on_kpi`.

## 5.4.0 - 2026-02-24

### Added

- Added optional SHACL validation during `kg_build` graph sync (per graph) controlled by profile settings:
  - `shacl_validate_sync` / `SHACL_VALIDATE_SYNC`
  - `shacl_validate_mode` / `SHACL_VALIDATE_MODE` (`warn|strict`)
  - `shacl_shape_specs` / `SHACL_SHAPE_SPECS`
- Added in-run progress streaming hook on cloud workflow:
  - `run_cloud_workflow(..., on_progress=...)`
  - emits per-graph payloads with graph metrics and validation summary (when enabled).

### Changed

- `kg_build` KPI payload now includes validation aggregates with clear pass/fail naming:
  - `validation.total`
  - `validation.pass`
  - `validation.fail`
  - `validation.warnings.{count,sources}`
  - `validation.errors.{count,sources}`

## 5.3.1 - 2026-02-24

### Added

- Added `kg_build` run-level sync KPI aggregation for dataset-scoped entities patched during static template and callback graph writes:
  - `totals.total_entities`
  - `totals.type_assertions_total`
  - `totals.property_assertions_total`
  - `entities_by_type`
  - `properties_by_predicate`
- Added `ProfileImportProtocol.get_kpi_summary()` for direct protocol consumers.
- Added optional `on_kpi` callback argument to `run_cloud_workflow(...)` to emit a single end-of-run KPI payload.

### Changed

- `run_cloud_workflow(..., on_kpi=...)` now emits KPI summaries in both successful and failed runs (failed runs may emit partial aggregates).

## 5.3.0 - 2026-02-23

### Changed

- `kg_build` callback graph source annotation now sets `seovoc:source = "web-page-import"` on all URI-subject entities produced in the current callback payload, instead of only the root WebPage entity.
- Existing root annotation behavior is preserved as part of the broader URI-subject annotation pass; blank-node subjects remain excluded.

### Added

- Protocol regression coverage for source annotation on root and non-root entities, callback graphs without `WebPage`, and blank-node exclusion.

### Migration

- To backfill legacy entities that were previously patched without `seovoc:source`, re-run import/overwrite so entities are re-patched with the new annotation behavior.

## 5.2.1 - 2026-02-22

### Fixed

- `kg_build` exports inheritance now propagates `_base` manifests for graph-sync static template rendering when exports are defined at profile root (`profiles/_base/exports.toml(.j2|.liquid)`) with deterministic `_base` -> selected override precedence.
- Missing export-key template failures now include profile-aware lookup diagnostics (active profile, searched exports paths, loaded exports files, and `_base` load status).

### Added

- Regression coverage for `_base`-only exports inheritance, empty selected exports fallback, selected-key override precedence, and missing-export diagnostic failures.

## 5.2.0 - 2026-02-22

### Changed

- Standardized `kg_build` profile inheritance/override semantics across runtime settings and profile assets:
  - `postprocessor_runtime`: `profiles.<selected>` overrides `_base`, then SDK default.
  - `postprocessors.toml`: selected profile manifest is exclusive when present, else `_base`, else none.
  - templates and mappings: `_base` + selected path overlays with selected-file precedence by relative path.
  - exports: `_base` + selected key merge with selected key override.
- Added deterministic profile-resolution observability logs for effective runtime, selected postprocessor manifest, template/export merge summaries, and effective mapping configuration.

### Added

- Regression coverage for runtime inheritance, postprocessor manifest precedence, template/file overrides, exports key overrides, mappings inheritance/override behavior, and profile-specific backward compatibility.

## 5.1.2 - 2026-02-22

### Fixed

- Ingestion resolver now bypasses legacy `SHEETS_*` completeness validation when `INGEST_SOURCE` is explicitly set to a non-`sheets` source (for example `sitemap` or `urls`), preventing false `INGEST_SRC_SHEETS_CONFIG_INVALID` failures.
- Preserved strict sheets validation for explicit `INGEST_SOURCE=sheets` and auto/legacy source resolution.

### Added

- Resolver regression tests covering explicit non-sheets source bypass behavior and auto/sheets validation paths.

## 5.1.1 - 2026-02-20

### Breaking

- `kg_build` postprocessor context contract now exposes auth via `context.account_key` and no longer injects credentials into `context.account.key`.
- `context.settings` has been removed from postprocessor context. Use `context.profile["settings"]` instead.

### Fixed

- Ensured `kg_build` postprocessor context always carries runtime auth in `context.account_key` (resolved from profile/runtime config) and fails fast before processor execution when missing.
- Preserved full resolved/interpolated profile payload in postprocessor context (`context.profile`) across oneshot and persistent runtimes.
- Kept API base URL fallback on `context.profile["settings"]["api_url"]` with default `https://api.wordlift.io`.
- Redacted postprocessor credential fields from preserved debug payload artifacts (`output/postprocessor_debug/**/context.json`) to prevent secret leakage.

### Added

- Unit and integration coverage for postprocessor `account_key` propagation, profile-payload propagation, runner context reconstruction, fail-fast missing-key behavior, and debug-payload secret redaction/log non-leak assertions.

## 5.0.0 - 2026-02-19

### Breaking

- Introduced a formal 2-axis ingestion model in SDK:
  - source axis (`INGEST_SOURCE`)
  - loader axis (`INGEST_LOADER`)
- Global default loader is now `web_scrape_api`.
- Added deterministic source auto-priority (`URLS > SITEMAP_URL > SHEETS_* > local`).
- Added explicit passthrough precedence rule for embedded HTML (`INGEST_PASSTHROUGH_WHEN_HTML=true`).

### Added

- New ingestion module: `wordlift_sdk.ingestion`
  - adapter contracts (`SourceAdapter`, `LoaderAdapter`)
  - shared models (`SourceItem`, `LoadedPage`)
  - source/loader registries and orchestrator
  - source adapters (`urls`, `sitemap`, `sheets`, `local`)
  - loader adapters (`simple`, `proxy`, `playwright`, `premium_scraper`, `web_scrape_api`, `passthrough`)
- Structured, machine-parseable warnings/events and typed config/runtime errors.
- Compatibility mapping and alias support:
  - `WEB_PAGE_IMPORT_MODE`: `default -> web_scrape_api`, `proxy -> proxy`, `premium_scraper -> premium_scraper`
  - source alias `debug-cloud <-> local`
- New ingestion docs/specs and contract tests.

### Changed

- `ApplicationContainer.create_url_source()` now resolves source selection through the ingestion resolver/registry bridge.
- `KgBuildApplicationContainer` web-page scrape path now bridges through ingestion execution while preserving protocol callback behavior.

## 4.0.2 - 2026-02-19

### Fixed

- Refreshed `poetry.lock` to use `virtualenv==20.38.0`, resolving GitHub Actions publish failures caused by unavailable `virtualenv==20.37.0` candidates.

## 4.0.1 - 2026-02-19

### Fixed

- Replaced private `pydantic_core._pydantic_core.ValidationError` retry exception references with the public `pydantic_core.ValidationError` path for Python 3.14 warning compatibility.

## 3.10.0 - 2026-02-18

### Fixed

- Hardened `HtmlConverter` sanitation for XML 1.0 safety in XPath materialization:
  - removes comment/processing-instruction nodes that can produce XML-invalid tokens
  - validates serialized XHTML with `ElementTree.fromstring()`
  - runs strict fallback sanitation on parse failures
  - raises context-rich line/column errors if output remains invalid

### Added

- Unit coverage for XML-invalid token sanitation in converter output.
- Integration coverage for XPath materialization using converter-sanitized XHTML with invalid-token input patterns.

## 3.9.0 - 2026-02-18

### Fixed

- Sanitized XHTML namespace safety in `HtmlConverter` to prevent
  `xml.etree.ElementTree.ParseError: unbound prefix` during `morph-kgc`
  XPath materialization:
  - undeclared prefixed tag names are rewritten to local names
  - undeclared prefixed attributes are removed
  - declared prefixes and `xml:*` attributes are preserved

### Added

- Unit coverage for undeclared-prefix sanitation in `HtmlConverter`.
- Integration-style coverage validating `__XHTML__~xpath` materialization with
  converter-sanitized XHTML containing undeclared prefixes.

## 3.6.0 - 2026-02-14

### Changed

- Stopped injecting SDK package paths into postprocessor subprocess `PYTHONPATH`.
- `kg_build` postprocessors now run with inherited environment only, requiring
  configured interpreters to resolve their own dependencies.

### Added

- Added postprocessor contract test coverage to assert no `PYTHONPATH`
  environment override is passed to subprocess execution.

## 3.4.0 - 2026-02-12

### Changed

- Restored `kg_build` URL-handler parity with the legacy workflow by executing
  `WebPageImportUrlHandler` plus optional `SearchConsoleUrlHandler` when
  `GOOGLE_SEARCH_CONSOLE` is enabled (default `True`).

### Added

- Added `kg_build` container tests validating:
  - Search Console handler is included by default.
  - Search Console handler is skipped when `GOOGLE_SEARCH_CONSOLE=False`.
  - `KgBuildApplicationContainer` still passes the configured protocol callback
    to `WebPageImportUrlHandler`.

## 3.3.0 - 2026-02-12

### Breaking

- Integrated `wordlift_sdk.kg_build` as the SDK-owned profile pipeline and removed candidate naming/API aliases from the public module surface.
- Enforced hard cutover to manifest-based postprocessor orchestration only; legacy `.py` and `*.command.toml` discovery is not supported.

### Added

- Included `wordlift_sdk.kg_build` package modules for profile config loading, cloud workflow orchestration, callback protocol, ID policy/allocation, YARRRML validation, and postprocessor subprocess execution.
- Added SDK docs/specs for profile runtime contracts:
  - `docs/CUSTOMER_PROJECT_CONTRACT.md`
  - `specs/PROFILE_CONFIG.md`
  - `specs/PIPELINE_ARCHITECTURE.md`
- Added dedicated postprocessor contract tests for:
  - base + profile manifest merge ordering
  - subprocess execution
  - N-Quads input/output exchange
  - fail-fast behavior
  - `enabled`, `python`, `timeout_seconds`, `keep_temp_on_error`
- Added direct dependency `jinja2` for Jinja-based KG template rendering.

## 3.2.0 - 2026-02-11

### Breaking

- Refactored structured data materialization to a generic, mapping-preserving pipeline.
- Removed legacy `yarrrml-parser` transpilation from execution path; YARRRML now runs directly through `morph-kgc` native support.
- Removed specialized review-centric behavior from core pipeline execution, including implicit `Review`/`Thing` coercions and review-specific postprocessing hooks.
- Removed `target_type` from `MaterializationPipeline.normalize(...)`, `MaterializationPipeline.postprocess(...)`, and `MaterializationPipeline.run(...)`.
- Removed deprecated `target_type` handling from generic `postprocess_jsonld(...)`.

### Added

- Runtime token replacement before direct materialization execution:
  - `__XHTML__` -> local XHTML source path
  - `__URL__` -> canonical URL resolved from `response.web_page.url` then explicit `url`
  - `__ID__` -> entity IRI resolved from `response.id`
- Strict URL token mode (`strict_url_token=True`) to fail on unresolved `__URL__` tokens.
- Fail-closed ID token handling when `__ID__` is present and unresolved.
- Explicit mapping error categories for malformed YARRRML and unsupported XPath/function constructs.

### Rationale

The SDK core now behaves as a reusable materialization engine for customer-authored mappings, without project-specific semantic assumptions.

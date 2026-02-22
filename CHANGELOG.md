# Changelog

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

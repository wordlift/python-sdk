# AGENTS

## Project Notes

- Generated Google SHACLs scope contained type requirements under container types
  (for example `ItemList`/`BreadcrumbList` → `ListItem`, `QAPage`/`FAQPage`/`Quiz`
  → `Question`/`Answer`/`Comment`, `ProfilePage` → `Person`/`Organization`,
  `Product` → `Offer`/`AggregateOffer`/`Review`/`AggregateRating`, `Recipe` → `HowToStep`,
  `Course` → `Organization`/`CreativeWork`, `Review` → `Rating`/`AggregateRating`/
  `ItemList`) when both appear in a feature definition. This prevents constraints
  from firing on unrelated nodes.
- The SHACL generator detects "one of" requirements in Google Search Gallery docs
  and emits `sh:or` constraints so any listed property satisfies the requirement.
- Python support is validated against 3.10–3.14; ensure tests pass on 3.14 before
  bumping the range.
- Schema.org grammar checks are deliberately permissive, accepting URL/text literals
  for all properties.
- URL validation can render pages with Playwright, extract JSON-LD fragments, and
  validate them via SHACL. Playwright browser binaries must be installed.
- SSL verification is always enabled; on macOS the SDK uses the system CA bundle
  when available and falls back to `certifi`. Explicit CA bundle overrides are
  supported in the SDK layer.
- Structured data materialization is mapping-preserving by default: no synthetic
  remapping to `ex:*`, no implicit `Review`/`Thing` coercion, and no review-specific
  postprocessing hooks in the generic pipeline.
- Runtime mapping tokens are supported in materialization input:
  `__XHTML__` (local XHTML source path), `__URL__` (resolved from
  `response.web_page.url` first, then explicit `url` argument; non-strict mode warns
  and keeps unresolved tokens), and `__ID__` (resolved from `response.id`;
  unresolved usage fails closed).
- Structured data materialization executes YARRRML directly with `morph-kgc`
  native support; legacy `yarrrml-parser` transpilation is not used.
- `HtmlConverter` sanitizes undeclared namespace prefixes before XHTML
  materialization (`prefix:tag` -> `tag`, undeclared prefixed attributes
  removed) to avoid XML parser `unbound prefix` failures with XPath sources;
  it also removes XML-invalid comments/PIs, validates output with
  `ElementTree.fromstring()`, and applies strict fallback sanitation on parse
  failures.
- Materialization errors are categorized with actionable context for malformed
  YARRRML and unsupported XPath/function constructs.
- `wordlift_sdk.kg_build` is integrated in the SDK with manifest-based
  postprocessor orchestration only; legacy `.py`/`*.command.toml` discovery
  is intentionally removed.
- `wordlift_sdk.kg_build` URL handling uses `WebPageScrapeApi` and conditionally
  runs Search Console refresh when `GOOGLE_SEARCH_CONSOLE` is enabled, while
  the legacy `ApplicationContainer` workflow continues to use web page imports.
- Ingestion resolver requires explicit `INGEST_SOURCE` and `INGEST_LOADER`;
  legacy fallback from `WEB_PAGE_IMPORT_MODE`/`WEB_PAGE_IMPORT_TIMEOUT` and
  implicit source auto-priority are intentionally removed.
- `wordlift_sdk.kg_build` callback patch preparation annotates every URI-subject
  node in the generated callback graph with `seovoc:source = "web-page-import"`
  (blank nodes are excluded), so source-filtered lookups continue to work when
  profile postprocessing removes/rewrites `WebPage` root nodes.
- `wordlift_sdk.kg_build` tracks run-level graph-sync KPIs from dataset-scoped
  entities actually patched in callback/static graphs (`total_entities`,
  `type_assertions_total`, `property_assertions_total`, `entities_by_type`,
  `properties_by_predicate`) plus optional SHACL validation aggregates
  (`validation.total/pass/fail`, warnings/errors count+sources), exposed via
  protocol `get_kpi_summary()` and cloud-flow `on_kpi` callback.
- `wordlift_sdk.kg_build` can stream in-run per-graph progress payloads
  (graph metrics and optional validation summary) via cloud-flow
  `on_progress` callback.
- In `wordlift_sdk.kg_build` strict SHACL mode, failing graph/static-template
  progress payloads are emitted before raising so failure context is available
  in telemetry; final KPI payload uses `validation = null` when SHACL sync
  validation is disabled.
- `wordlift_sdk.kg_build` postprocessor subprocesses do not inject package paths
  into `PYTHONPATH`; configured interpreters must resolve their own dependencies.
- `wordlift_sdk.kg_build` postprocessor runtime is configurable via
  `postprocessor_runtime` with deterministic inheritance
  (`profiles.<name>` -> `profiles._base` -> `persistent` default); `persistent`
  keeps one long-lived worker per class across callbacks.
- Worai-facing cloud orchestration is standardized on
  `wordlift_sdk.kg_build.cloud_flow.run_cloud_workflow` as canonical path.
- `wordlift_sdk.kg_build` postprocessor manifests use file-level precedence:
  profile manifest (`profiles/<name>/postprocessors.toml`) is exclusive when
  present, otherwise `_base` is used.
- `wordlift_sdk.kg_build` exports inheritance for template/mapping rendering
  loads `_base` then selected profile manifests with key-level selected override;
  supported files remain `exports.toml`, `exports.toml.j2`, and
  `exports.toml.liquid` in profile root and (backward-compatible) templates
  directories.
- `wordlift_sdk.kg_build` postprocessor context keeps `account` as the clean
  API `/me` object, exposes auth as `context.account_key`, and provides resolved
  profile config via `context.profile`; API base URL must be read from
  `context.profile["settings"]["api_url"]` (default `https://api.wordlift.io`).
  Debug payload copies redact key fields.
- Retry handlers reference `pydantic_core.ValidationError` via the public API
  (not `pydantic_core._pydantic_core.ValidationError`) for Python 3.14
  compatibility.
- SDK ingestion now supports a 2-axis adapter model (`source` + `loader`) with
  registry-based resolution, deterministic auto rules, and legacy compatibility
  mapping (`WEB_PAGE_IMPORT_MODE default -> web_scrape_api`, `proxy -> proxy`,
  `premium_scraper -> premium_scraper`); `local` and `debug-cloud` source names
  are treated as aliases.
- Ingestion resolver skips legacy `SHEETS_*` completeness validation when
  `INGEST_SOURCE` is explicitly set to a non-`sheets` source; strict sheets
  validation is still enforced for explicit `sheets` and auto/legacy detection.
- Legacy container/workflow integration now bridges source selection through the
  ingestion resolver/registry, and `kg_build` web-page scrape handling runs via
  ingestion loader execution before invoking profile callbacks.
- Playwright ingestion failures preserve existing top-level loader error
  code/message (`INGEST_LOAD_BROWSER_ERROR`, `Playwright loader failed for <url>`)
  while attaching structured root-cause diagnostics in `LoaderRuntimeError.details`
  and emitted `ingest.item_failed.meta` (`root_exception_type`,
  `root_exception_message` capped to 2KB, `phase`, `url`, `wait_until`,
  `timeout_ms`, `headless`).

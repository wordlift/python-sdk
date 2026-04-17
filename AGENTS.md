# AGENTS

## Project Notes

- Patch-release hygiene: keep `pyproject.toml`, `poetry.lock`,
  `CHANGELOG.md`, `README.md`, `docs/INDEX.md`, and `specs/INDEX.md`
  synchronized for every tagged patch release.
- Packaging is slice-based as of v7: `wordlift-sdk` installs a lean base by
  default and exposes optional extras (`core`, `render`, `validation`,
  `google-sheets`, `google-search-console`, `ingestion`, `structured-data`,
  `workflow`, `graph`, `kg-build`, `legacy`, `all`) while preserving the
  `wordlift_sdk.*` import namespace through lazy package exports.
- Slice verification is part of the repository contract: keep
  `tests/tools/run_slice_smoke_imports.py`,
  `tests/tools/run_slice_tests.py`, and
  `tests/tools/check_missing_extra_hints.py` aligned with any public packaging
  or dependency-boundary change.
- Ingestion now exposes source-only URL discovery via
  `wordlift_sdk.ingestion.resolve_ingestion_source_items`, reusing resolver,
  source adapters, URL filtering, and warning event semantics from the shared
  ingestion stack.
- Structured-data inventory generation is available in SDK ingestion via
  `wordlift_sdk.ingestion.create_structured_data_inventory_from_ingestion`,
  including inventory row construction (`faq_markup`, `faq_markup_from_graph`,
  `types`, merged `structured_data`) over shared ingestion source+loader runs.
  Inventory uses a single source-resolution pass (no duplicate sitemap/source
  traversal) by reusing resolved items for ingestion.
  Inventory generation also emits optional host-facing progress callbacks
  (`inventory.progress.started|updated|completed`) via
  `on_progress(payload)` so CLI/UI layers can render progress bars without
  SDK-owned terminal output; `updated` starts during ingestion
  (`ingest.item_loaded`/`ingest.item_failed` mapping), not only after
  ingestion completes.
- Generated Google SHACLs scope contained type requirements under container types
  (for example `ItemList`/`BreadcrumbList` → `ListItem`, `QAPage`/`FAQPage`/`Quiz`
  → `Question`/`Answer`/`Comment`, `ProfilePage` → `Person`/`Organization`,
  `Product` → `Offer`/`AggregateOffer`/`Review`/`AggregateRating`, `Recipe` → `HowToStep`,
  `Course` → `Organization`/`CreativeWork`, `Review` → `Rating`/`AggregateRating`/
  `ItemList`) when both appear in a feature definition. This prevents constraints
  from firing on unrelated nodes.
- The SHACL generator detects "one of" requirements in Google Search Gallery docs
  and emits `sh:or` constraints so any listed property satisfies the requirement.
- The SHACL generator treats explicit table option branches (for example
  `Option A` / `Option B`) as branch-level alternatives, supports multi-property
  branches, and ignores enum URL literals when extracting property alternatives.
- The SHACL generator treats explicit fallback wording in required rows (for
  example, `url` supported when `contentUrl` is omitted) as `sh:or`
  alternatives rather than hard-requiring only the preferred property.
- The SHACL generator treats recommended-table "choose either ... or ..."
  alternatives as warning-level `sh:or` constraints (including scoped/nested
  types), warning only when all alternatives are absent (for example, Merchant
  listing `DefinedRegion`, Merchant listing shipping rate value/maxValue, and
  Product snippet offer currency path alternatives).
- The SHACL generator ignores paragraph-level "one of the following values"
  lists when building property alternatives, and downgrades conditional
  required prose ("required when/if", "only required if") to warning-level
  constraints to avoid unconditional errors for context-dependent sections.
- Google SHACL type-context parsing is now constrained to explicit type
  definitions (`must be based on one of the following schema.org types`,
  `full definition of ... is available/provided`) and scoped plain headings
  (for example `Quiz`, `Question`, `DataFeed entity`) so example markup
  fragments do not leak nested/example types into feature-level constraints.
- Search Gallery sample fixtures are maintained under
  `tests/fixtures/search_gallery/` via
  `python tests/tools/extract_search_gallery_samples.py`; the latest
  page-by-page review artifact is `docs/search_gallery_shacl_review.md`.
- Search Gallery quality gates include committed per-page conformance baseline
  (`tests/fixtures/search_gallery/baseline_conformance.json`), explicit known
  non-conforming sample IDs (`tests/fixtures/search_gallery/expectations.json`),
  and CI regression diff reporting via
  `python tests/tools/search_gallery_conformance_diff.py`.
- Google Search Console canonical selection is available via
  `wordlift_sdk.google_search_console.create_canonical_csv_from_gsc_impressions`:
  input CSV (`url,title`) with optional URL regex filtering, interval parsing
  (`XX[d|w|m]`), exact-title clustering, canonical election by highest
  impressions (tie -> first input row), and fixed/`auto` adaptive request
  concurrency.
- Shared adaptive concurrency policy is centralized in
  `wordlift_sdk.utils.auto_concurrency.AutoConcurrencyController` and reused by
  `structured_data.batch` (and GSC canonical selection), with throttle/server
  failures/errors reducing concurrency and all-OK batches increasing it within
  configured bounds.
- Python support is validated against 3.10–3.14; ensure tests pass on 3.14 before
  bumping the range.
- Schema.org grammar checks are deliberately permissive, accepting URL/text literals
  for all properties.
- Schema.org grammar issue extraction is subclass-aware for range checks:
  warnings like `Schema.org range check: priceSpecification.` are suppressed
  when the value node type is a valid schema.org subclass of the expected
  class (for example `UnitPriceSpecification` under `PriceSpecification`).
- URL validation can render pages with Playwright, extract JSON-LD fragments, and
  validate them via SHACL. Playwright browser binaries must be installed.
- Validation exposes SDK-level shape composition (`resolve_shape_specs`) with
  bundled include/exclude controls and extra local/remote SHACL overlays, plus
  normalized issue extraction/filtering helpers with stable issue fields
  (`rule_id`, `rule_set`) for host-side UX/CLI layers.
- Bundled validation defaults treat `google-image-license-metadata` as opt-in
  (excluded unless explicitly requested in `shape_specs` / `builtin_shapes`).
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
  failures. The converter also strips default XHTML `xmlns` declarations so
  unprefixed XPath selectors against `__XHTML__` (for example `.//div`) match
  as expected.
- Materialization errors are categorized with actionable context for malformed
  YARRRML and unsupported XPath/function constructs.
- `wordlift_sdk.kg_build` is integrated in the SDK with manifest-based
  postprocessor orchestration only; legacy `.py`/`*.command.toml` discovery
  is intentionally removed.
- `wordlift_sdk.kg_build` URL handling uses `WebPageScrapeApi` and conditionally
  runs Search Console refresh when `GOOGLE_SEARCH_CONSOLE` is enabled, while
  the legacy `ApplicationContainer` workflow continues to use web page imports.
- `wordlift_sdk.kg_build` ingestion bridge suppresses callback emission for
  pages with HTTP error statuses (`status_code >= 400`), raising per-URL handler
  errors so downstream import/graph processing is skipped for not-found/server
  error pages.
- Ingestion resolver requires explicit `INGEST_SOURCE` and `INGEST_LOADER`;
  legacy fallback from `WEB_PAGE_IMPORT_MODE`/`WEB_PAGE_IMPORT_TIMEOUT` and
  implicit source auto-priority are intentionally removed.
- Sitemap ingestion source discovery (`SitemapSourceAdapter`) sets
  browser-like request headers for `advertools.sitemaps.sitemap_to_df`
  (`User-Agent`, `Accept`, `Accept-Language`, `Referer`,
  `Upgrade-Insecure-Requests`, `Sec-CH-*`) so sitemap fetch identity is closer
  to Playwright/browser ingestion defaults.
- `wordlift_sdk.kg_build` callback patch preparation annotates first-level
  URI-subject nodes in the generated callback graph with
  `seovoc:source = "web-page-import"` using dataset ID depth
  `/<dataset>/<bucket>/<id>` as first-level (deeper child URI nodes and blank
  nodes are excluded), so source-filtered lookups continue to work when
  profile postprocessing removes/rewrites `WebPage` root nodes.
- `wordlift_sdk.kg_build` computes per-node `seovoc:importHash` before patching
  dataset-scoped nodes (excluding `seovoc:importHash` from hash input), writes the
  computed value back to the node, and applies `import_hash_mode` (`on|write|off`)
  for unchanged-node skip behavior.
- `wordlift_sdk.kg_build` canonical ID generation for callback-emitted graphs now
  includes a fallback subject-IRI rewrite pass: all URIRef subjects are
  canonicalized unless already under canonical dataset root prefixes; static
  template patching remains separate.
- `wordlift_sdk.kg_build` callback ordering runs customer postprocessors before
  built-in canonical ID generation, so IDs minted or rewritten in local
  postprocessing are canonicalized in the final graph before sync patching.
- `wordlift_sdk.kg_build` canonical ID generation nests `schema:Action` subjects
  under canonical parent subject IRIs when linked via
  `schema:potentialAction`/`schema:action` (for example
  `<parent>/actions/<slug>`).
- `wordlift_sdk.kg_build` canonical ID generation supports optional lookup-based
  root IRI reuse via `Context.extensions["kg_build.iri_lookup"]`
  (`IriLookup.iri_for_subject(graph, subject)`), with root-only application
  so dependent nodes still follow canonical parent-nesting rules.
- `wordlift_sdk.kg_build` tracks run-level graph-sync KPIs from dataset-scoped
  entities actually patched in callback/static graphs (`total_entities`,
  `type_assertions_total`, `property_assertions_total`, `entities_by_type`,
  `properties_by_predicate`) plus optional SHACL validation aggregates
  (`validation.total/pass/fail`, warnings/errors count+sources), exposed via
  protocol `get_kpi_summary()` and cloud-flow `on_kpi` callback.
- `wordlift_sdk.kg_build` can stream in-run per-graph progress payloads
  (graph metrics and optional validation summary) via cloud-flow
  `on_progress` callback.
- In `wordlift_sdk.kg_build` fail SHACL mode, failing graph/static-template
  progress payloads are emitted before raising so failure context is available
  in telemetry; final KPI payload uses `validation = null` when SHACL sync
  validation is disabled.
- `wordlift_sdk.kg_build` static template bootstrap is concurrency-safe:
  static templates are patched exactly once per run and only one
  `on_progress` payload with `kind="static_templates"` is emitted at startup.
- `wordlift_sdk.kg_build` debug-cloud callback artifacts now include per-URL
  source snapshots (`<sha256(url)>.html`, `<sha256(url)>.xhtml`)
  in addition to callback graph Turtle output.
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
- Ingestion URL filtering is now standardized on global `URL_REGEX` (applied
  across `urls|sitemap|sheets|local` before loader execution); sitemap-specific
  `SITEMAP_URL_PATTERN` is deprecated and mapped as alias when `URL_REGEX` is
  unset.
- Graph-sync URL sourcing now enforces resolved ingestion URL scoping in
  `AdapterUrlSource` before `NewOrChangedUrlSource` GraphQL lookup, so
  out-of-scope sitemap URLs are excluded from `new_or_changed` consideration
  and import requests.
- Ingestion exposes local CLI type classification export via
  `create_type_classification_csv_from_ingestion`, using `trafilatura` markdown
  extraction, optional host-facing progress callbacks
  (`type_classification.progress.started|updated|completed`), and
  non-interactive local CLI auto-selection
  (`claude` -> `codex` -> `gemini`).
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
- Playwright ingestion is async-loop-safe in cloud workflows: when a caller thread
  already runs an asyncio event loop, rendering is offloaded away from that thread
  before Sync Playwright APIs are invoked.
- Playwright ingestion default `wait_until` is `domcontentloaded` (override with
  `PLAYWRIGHT_WAIT_UNTIL`), and navigation timeout now falls back to partial DOM
  extraction instead of immediate loader failure.
- `IngestionWebPageScrapeUrlHandler` now surfaces first failure diagnostics from
  `ingest.item_failed.meta` in raised/logged errors as parseable JSON
  (`diagnostics=<json>`), with whitelisted keys and truncation/sanitization.

 # WordLift Python SDK

A Python toolkit for orchestrating WordLift imports: fetch URLs from sitemaps, Google Sheets, or explicit lists, filter out already imported pages, enqueue search console jobs, push RDF graphs, and call the WordLift APIs to import web pages.

## Features
- URL sources: XML sitemaps (with optional regex filtering), Google Sheets (`url` column), or Python lists.
- Change detection: skips URLs that are already imported unless `OVERWRITE` is enabled; re-imports when `lastmod` is newer.
- Web page imports: sends URLs to WordLift with embedding requests, output types, retry logic, and pluggable callbacks.
- Python 3.14 compatibility: retry filters use `pydantic_core.ValidationError` via the public API.
- Search Console refresh: triggers analytics imports when top queries are stale.
- Graph templates: renders `.ttl.liquid` templates under `data/templates` with account data and uploads the resulting RDF graphs.
- Extensible: override protocols via `WORDLIFT_OVERRIDE_DIR` without changing the library code.

## Installation

```bash
pip install wordlift-sdk
# or
poetry add wordlift-sdk
```

Requires Python 3.10–3.14.

## Configuration

Settings are read in order: `config/default.py` (or a custom path you pass to `ConfigurationProvider.create`), environment variables, then (when available) Google Colab `userdata`.

Common options:
- `WORDLIFT_KEY` (required): WordLift API key.
- `API_URL`: WordLift API base URL, defaults to `https://api.wordlift.io`.
- `SITEMAP_URL`: XML sitemap to crawl; `SITEMAP_URL_PATTERN` optional regex to filter URLs.
- `SHEETS_URL`, `SHEETS_NAME`, `SHEETS_SERVICE_ACCOUNT`: use a Google Sheet as source; service account points to credentials file.
- `URLS`: list of URLs (e.g., `["https://example.com/a", "https://example.com/b"]`).
- `OVERWRITE`: re-import URLs even if already present (default `False`).
- `WEB_PAGE_IMPORT_WRITE_STRATEGY`: WordLift write strategy (default `createOrUpdateModel`).
- `EMBEDDING_PROPERTIES`: list of schema properties to embed.
- `WEB_PAGE_TYPES`: output schema types, defaults to `["http://schema.org/Article"]`.
- `GOOGLE_SEARCH_CONSOLE`: enable/disable Search Console handler (default `True`).
- `CONCURRENCY`: max concurrent handlers, defaults to `min(cpu_count(), 4)`.
- `WORDLIFT_OVERRIDE_DIR`: folder containing protocol overrides (default `app/overrides`).

## TLS/SSL

The SDK enforces SSL verification. On macOS it uses the system CA bundle when available and falls back to `certifi` if needed. You can override the CA bundle path explicitly in code:

```python
from wordlift_sdk.client import ClientConfigurationFactory
from wordlift_sdk.structured_data import CreateRequest

factory = ClientConfigurationFactory(
    key="your-api-key",
    api_url="https://api.wordlift.io",
    ssl_ca_cert="/path/to/ca.pem",
)
configuration = factory.create()

request = CreateRequest(
    url="https://example.com",
    target_type="Thing",
    output_dir=Path("."),
    base_name="structured-data",
    jsonld_path=None,
    yarrml_path=None,
    api_key="your-api-key",
    base_url=None,
    ssl_ca_cert="/path/to/ca.pem",
    debug=False,
    headed=False,
    timeout_ms=30000,
    max_retries=2,
    quality_check=True,
    max_xhtml_chars=40000,
    max_text_node_chars=400,
    max_nesting_depth=2,
    verbose=True,
    validate=True,
    wait_until="networkidle",
)
```

Note: `target_type` is used for agent guidance and validation shape selection. The YARRRML materialization pipeline now preserves authored mapping semantics and does not coerce nodes to `Review`/`Thing`.

Example `config/default.py`:

```python
WORDLIFT_KEY = "your-api-key"
SITEMAP_URL = "https://example.com/sitemap.xml"
SITEMAP_URL_PATTERN = r"^https://example.com/article/.*$"
GOOGLE_SEARCH_CONSOLE = True
WEB_PAGE_TYPES = ["http://schema.org/Article"]
EMBEDDING_PROPERTIES = [
    "http://schema.org/headline",
    "http://schema.org/abstract",
    "http://schema.org/text",
]
```

## Running the import workflow

```python
import asyncio
from wordlift_sdk import run_kg_import_workflow

if __name__ == "__main__":
    asyncio.run(run_kg_import_workflow())
```

The workflow:
1. Renders and uploads RDF graphs from `data/templates/*.ttl.liquid` using account info.
2. Builds the configured URL source and filters out unchanged URLs (unless `OVERWRITE`).
3. Sends each URL to WordLift for import with retries and optional Search Console refresh.

You can build components yourself when you need more control:

```python
import asyncio
from wordlift_sdk.container.application_container import ApplicationContainer

async def main():
    container = ApplicationContainer()
    workflow = await container.create_kg_import_workflow()
    await workflow.run()

asyncio.run(main())
```

## Custom callbacks and overrides

Override the web page import callback by placing `web_page_import_protocol.py` with a `WebPageImportProtocol` class under `WORDLIFT_OVERRIDE_DIR` (default `app/overrides`). The callback receives a `WebPageImportResponse` and can push to `graph_queue` or `entity_patch_queue`.

## Templates

Add `.ttl.liquid` files under `data/templates`. Templates render with `account` fields available (e.g., `{{ account.dataset_uri }}`) and are uploaded before URL handling begins.

## Validation

SHACL validation utilities and generated Google Search Gallery shapes are included. When a feature includes both container types (for example `ItemList`, `BreadcrumbList`, `QAPage`, `FAQPage`, `Quiz`, `ProfilePage`, `Product`, `Recipe`, `Course`, `Review`) and their contained types (`ListItem`, `Question`, `Answer`, `Comment`, `Offer`, `AggregateOffer`, `HowToStep`, `Person`, `Organization`, `Rating`, `AggregateRating`, `Review`, `ItemList`), the generator scopes the contained constraints under the container properties to avoid enforcing them on unrelated nodes. For Product snippets, `offers` is scoped as `Offer` or `AggregateOffer`, matching Google requirements. The generator also captures "one of" requirements expressed in prose lists and emits `sh:or` constraints so any listed property satisfies the requirement. For tables with explicit `Option A` / `Option B` branches, the generator emits branch-level alternatives (a branch can require multiple properties), and it ignores enum URL literals when extracting property alternatives. Schema.org grammar checks are intentionally permissive and accept URL/text literals for all properties.
The generator also recognizes explicit fallback wording in required rows (for example, `contentUrl` with supported `url` fallback if `contentUrl` is missing) and emits `sh:or` alternatives instead of hard-requiring only the preferred property.
Paragraph-level "one of the following values" lists are treated as value guidance (not property alternatives), and conditional sections phrased as "required when"/"required if" are emitted as warnings instead of unconditional required errors.
Google page type context is resolved from explicit type-definition prose and scoped plain headings (for example `Quiz`, `Question`, `DataFeed entity`) to avoid example-snippet schema types leaking into top-level feature constraints.
Search Gallery fixtures are maintained in `tests/fixtures/search_gallery`; use
`python tests/tools/extract_search_gallery_samples.py` to refresh samples and
`python tests/tools/search_gallery_conformance_diff.py` to print per-page
baseline conformance deltas used by CI quality gates.

Use `wordlift_sdk.validation.validate_jsonld_from_url` to render a URL with Playwright, extract JSON-LD fragments, and validate them against SHACL shapes.

For SDK-side shape selection, use `wordlift_sdk.validation.resolve_shape_specs`
to compose bundled include/exclude sets and extra local/remote SHACL overlays:

```python
from wordlift_sdk.validation import resolve_shape_specs, validate_file

shape_specs = resolve_shape_specs(
    builtin_shapes=["google-article"],
    exclude_builtin_shapes=["schemaorg-grammar"],
    extra_shapes=["./custom-shape.ttl", "https://example.com/custom-shape.ttl"],
)
result = validate_file("out/page.jsonld", shape_specs=shape_specs)
```

Default bundled-shape resolution excludes `google-image-license-metadata`; include
it explicitly with `resolve_shape_specs(builtin_shapes=["google-image-license-metadata"])`
or by passing `shape_specs=["google-image-license-metadata"]`.

Playwright is required for URL rendering. After installing dependencies, install the browser binaries:

```bash
poetry run playwright install
```

## Structured Data Tokens

YARRRML mappings are now executed directly by `morph-kgc` native YARRRML support.
There is no JS transpile step via `yarrrml-parser`, and no temporary `mapping.ttl`
conversion artifact in the materialization pipeline.

Customer-authored mappings can use runtime tokens:
- `__XHTML__` for the local XHTML source path used by materialization.
- `__URL__` for canonical page URL injection.
- `__ID__` for callback/import entity IRI injection.

`__URL__` resolution order is:
1. `response.web_page.url`
2. explicit `url` argument passed to materialization

`__ID__` resolution source is:
1. `response.id` (legacy import callbacks)
2. `existing_web_page_id` injected by `kg_build` scrape callbacks

When unresolved:
- strict mode (`strict_url_token=True`): fail fast
- default non-strict mode: warn and keep `__URL__` unchanged
- `__ID__`: fail closed with an explicit error

Recommendation: use `__ID__` in subject/object IRI positions instead of
temporary hardcoded page subjects such as `{{ dataset_uri }}/web-pages/page`.

Compatibility note: `morph-kgc` native YARRRML behavior may differ from legacy
JS parser behavior for some advanced XPath/function constructs.

When preparing XHTML sources from raw HTML, `HtmlConverter` strips undeclared
namespace prefixes from tag names and removes undeclared prefixed attributes to
avoid `xml.etree.ElementTree.ParseError: unbound prefix` failures in XPath
materialization flows.
It also removes XML-invalid comments/processing instructions, validates output
with `xml.etree.ElementTree.fromstring()`, and runs a strict fallback sanitation
pass before surfacing a context-rich conversion error.
Converted XHTML also strips default `xmlns` declarations so unprefixed XPath
selectors (for example `.//div`, `.//h1`) work with `__XHTML__` sources.

## KG Build Module

The SDK now includes a profile-driven cloud mapping module under `wordlift_sdk.kg_build`.

- Public module import: `wordlift_sdk.kg_build`
- Canonical cloud orchestration path: `wordlift_sdk.kg_build.cloud_flow.run_cloud_workflow`
- Supported cloud source modes in canonical path:
  - `urls`
  - `sitemap_url` (optional `sitemap_url_pattern`)
  - `sheets_url` + `sheets_name`
- Postprocessor runner entrypoint: `python -m wordlift_sdk.kg_build.postprocessor_runner`
- Persistent postprocessor worker entrypoint: `python -m wordlift_sdk.kg_build.postprocessor_worker`
- URL handling parity with legacy workflow:
  - `WebPageScrapeUrlHandler` is always enabled for `kg_build`
  - `SearchConsoleUrlHandler` is enabled when `GOOGLE_SEARCH_CONSOLE=True` (default)
- Postprocessor manifest precedence:
1. `profiles/<profile>/postprocessors.toml` (exclusive when present)
2. fallback `profiles/_base/postprocessors.toml`
3. otherwise no postprocessors
- Execution is manifest-based only (hard cutover): no legacy `.py` or `*.command.toml` discovery.
- During callback patch preparation, the SDK annotates first-level URI-subject nodes in the generated graph with `seovoc:source "web-page-import"` where first-level is dataset ID depth `/<dataset>/<bucket>/<id>` (for example `https://data.host/dataset/types/name`); deeper child IDs and blank nodes are not annotated.
- Before patching each dataset-scoped node, the SDK computes a per-node `seovoc:importHash` from graph snapshot triples (excluding `seovoc:importHash` itself), writes the hash back to the node, and can skip API patching when a provided `seovoc:importHash` already matches.
- Import-hash behavior is controlled by `import_hash_mode` / `IMPORT_HASH_MODE`:
  - `on` (default): write hash + skip unchanged nodes
  - `write`: write hash but do not skip
  - `off`: disable hash write/skip
- Postprocessor runtime mode:
  - `profiles.<profile>.postprocessor_runtime` overrides `_base`.
  - `_base.postprocessor_runtime` is used when profile value is missing.
  - SDK default is `persistent`.
  - `persistent` keeps one long-lived subprocess per configured class and reuses it across callbacks.
- Template exports inheritance:
  - supported files: `exports.toml`, `exports.toml.j2`, `exports.toml.liquid`
  - lookup locations: profile root (`profiles/_base`, `profiles/<profile>`) and templates directories (backward compatible)
  - precedence: `_base` first, selected profile second; selected keys override `_base`
- Postprocessor authoring contract:
  - supported method: `process_graph(self, graph, context)`
  - supported return values: `Graph`, `None`, or an awaitable resolving to `Graph | None`
  - in persistent mode, each worker instance processes one job at a time (callbacks can still run concurrently across different workers/classes)
  - `context.profile` contains the resolved/interpolated profile object (including inherited fields)
  - `context.account_key` contains the runtime API key and is required for postprocessor execution
  - keep `context.account` as the clean `/me` account object (no injected key)
  - API base URL should be read from `context.profile["settings"]["api_url"]` (defaults to `https://api.wordlift.io`)
- Run-level sync KPIs:
  - `ProfileImportProtocol.get_kpi_summary()` returns:
    - graph totals: `total_entities`, `type_assertions_total`, `property_assertions_total`
    - graph breakdowns: `entities_by_type`, `properties_by_predicate`
    - validation totals: `validation.total`, `validation.pass`, `validation.fail` (when validation is enabled)
    - validation breakdowns: `validation.warnings.{count,sources}`, `validation.errors.{count,sources}` (when validation is enabled)
  - Validation can be enabled per profile with:
    - `shacl_validate_mode` / `SHACL_VALIDATE_MODE` (`off|warn|fail`, default `warn`)
    - `shacl_builtin_shapes` / `SHACL_BUILTIN_SHAPES` (optional bundled shape allowlist)
    - `shacl_exclude_builtin_shapes` / `SHACL_EXCLUDE_BUILTIN_SHAPES` (optional bundled shape denylist)
    - `shacl_extra_shapes` / `SHACL_EXTRA_SHAPES` (optional list/comma-separated local paths or remote URLs)
  - `run_cloud_workflow(..., on_kpi=...)` emits the final KPI summary once at run end (including failed runs with partial data).
  - `run_cloud_workflow(..., on_progress=...)` emits per-graph progress payloads during sync, including graph metrics and (when enabled) validation summaries.
  - static template bootstrap emits one startup `on_progress` payload (`kind="static_templates"`) and patches static templates once per run, even when URL callbacks run concurrently.
  - debug-cloud runs persist per-URL artifacts under `output/debug_cloud/<profile>/`:
    `<sha256(url)>.ttl`, `<sha256(url)>.html`, and `<sha256(url)>.xhtml`.
  - `run_cloud_workflow(..., on_info=...)` remains supported and can be used together with `on_progress`/`on_kpi`.
  - final KPI payload uses `validation = null` when SHACL sync validation is disabled.
  - migration notes and deprecation window for non-canonical behavior are documented in `docs/kg_build_cloud_workflow_migration.md`.

## Ingestion Module

The SDK now includes a reusable 2-axis ingestion module under `wordlift_sdk.ingestion`:

- Axis A (`INGEST_SOURCE`): `urls|sitemap|sheets|local`
- Axis B (`INGEST_LOADER`): `simple|proxy|playwright|premium_scraper|web_scrape_api|passthrough`

Default loader is `web_scrape_api`. If an item already includes embedded HTML and
`INGEST_PASSTHROUGH_WHEN_HTML=True` (default), ingestion uses `passthrough`
before network loaders.

`INGEST_SOURCE` and `INGEST_LOADER` are required. Legacy resolver fallback from
`WEB_PAGE_IMPORT_MODE`/`WEB_PAGE_IMPORT_TIMEOUT` is removed.
Playwright ingestion failures keep stable top-level code/message and expose root-cause
diagnostics (`root_exception_type`, `root_exception_message`, `phase`, `url`,
`wait_until`, `timeout_ms`, `headless`) in `ingest.item_failed.meta`.
When ingestion is triggered from async workflows, the Playwright loader avoids executing
Sync API calls directly on the active asyncio loop thread.
Default Playwright wait mode for ingestion is `domcontentloaded`; navigation timeouts now
return partial page HTML when available instead of failing immediately.
Bridge handler failures (`IngestionWebPageScrapeUrlHandler`) now preserve existing
loader code/message text and append parseable diagnostics from `ingest.item_failed.meta`
when available.

Quick start:

```python
from wordlift_sdk.ingestion import run_ingestion

result = run_ingestion(
    {
        "INGEST_SOURCE": "urls",
        "URLS": ["https://example.com"],
        "INGEST_LOADER": "web_scrape_api",
        "WORDLIFT_KEY": "your-api-key",
    }
)
```

## Testing

```bash
poetry install --with dev
poetry run pytest
```

## Documentation

- [Documentation Index](docs/INDEX.md): Quick index for all user and agent-facing docs.
- [Ingestion Pipeline](docs/ingestion_pipeline.md): 2-axis source/loader architecture and compatibility rules.
- [Public Entry Points](docs/public_entry_points.md): Task-oriented inventory of client APIs by module file.
- [Google Sheets Lookup](docs/google_sheets_lookup.md): Utility for O(1) lookups from Google Sheets.
- [Web Page Import](docs/web_page_import.md): Configure fetch options, proxies, and JS rendering.
- [KG Build KPI + Validation Callbacks](docs/kg_build_kpi_and_validation.md): Client contract and payload examples for `on_progress` and `on_kpi`.
- [KG Build Cloud Workflow Migration](docs/kg_build_cloud_workflow_migration.md): Canonical `run_cloud_workflow` migration steps, deprecation window, and source/runtime expectations.
- [Worai SDK Integration Contract v6](docs/worai_sdk_integration_contract_v6.md): Version-locked implementation contract for worai integrations on SDK 6.x.
- [Structured Data](docs/structured_data.md): Structured data architecture and pipeline behavior.
- [Canonical ID Policy](docs/canonical_id_policy.md): Scope strategy, deterministic type precedence, and URL-preserving rewrite guarantees.
- [Customer Project Contract](docs/CUSTOMER_PROJECT_CONTRACT.md): Profile repo contract and manifest-based postprocessor runtime.
- [Structured Data Spec](specs/structured_data.md): Internal technical details for runtime placeholder resolution.
- [Ingestion Pipeline Spec](specs/INGESTION_PIPELINE.md): Internal source/loader contract and precedence rules.
- [Profile Config Spec](specs/PROFILE_CONFIG.md): Profile inheritance, environment interpolation, and manifest postprocessor contract.
- [Pipeline Architecture Spec](specs/PIPELINE_ARCHITECTURE.md): `kg_build` runtime flow and callback architecture.
- [Migration Guide](MIGRATION.md): Breaking changes for structured data refactor.
- [Changelog](CHANGELOG.md): Versioned release notes.

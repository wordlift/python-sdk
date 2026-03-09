# Public Entry Points

Task-oriented reference for client-facing APIs in `wordlift_sdk`, organized by job and source file.

Conventions:
- `Path` means `pathlib.Path`.
- `log` means `Callable[[str], None]` (for example `print`).
- `| None` means nullable.

## Run YARRRML mappings on URLs

File: `wordlift_sdk/kg_build/rml_mapping.py`
- `RmlMappingService.apply_mapping(html, url, mapping_file_path, xhtml=None, mapping_content=None, response=None) -> Graph | None`
- Aim: Execute a YARRRML mapping against one page and return RDF triples.
- Parameters:
  - `html: str`: raw page HTML.
  - `url: str`: canonical page URL used during runtime token resolution.
  - `mapping_file_path: str | Path`: mapping path (used when `mapping_content` is omitted).
  - `xhtml: str | None`: pre-cleaned XHTML override; if omitted, HTML is converted internally.
  - `mapping_content: str | None`: mapping text override (bypasses file read).
  - `response: object | None`: callback payload used by runtime placeholders (`__URL__`, `__ID__`).
- Returns: RDF graph on success, `None` on mapping/runtime failure.

File: `wordlift_sdk/structured_data/orchestrator.py`
- `GenerateWorkflow.run(request, log) -> dict[str, object]`
- Aim: Apply one existing mapping file to multiple input URLs and write outputs.
- Parameters:
  - `request: GenerateRequest` with key fields:
  - `input_value: str`: URL source descriptor (URL list/sitemap/input source string).
  - `yarrrml_path: Path`: mapping file.
  - `regex: str`: URL filter regex.
  - `output_dir: Path`, `output_format: str`, `concurrency: str`.
  - `api_key: str | None`, `base_url: str | None`, `ssl_ca_cert: str | None`.
  - `headed: bool`, `timeout_ms: int`, `wait_until: str`.
  - `max_xhtml_chars: int`, `max_text_node_chars: int`, `max_pages: int | None`, `verbose: bool`.
  - `log: Callable[[str], None]`: progress callback.
- Returns: Summary dict with totals, successes, failures, output directory, and errors.

File: `wordlift_sdk/kg_build/cloud_flow.py`
- `run_cloud_workflow(*, config, configuration_provider_create, container_factory, protocol_factory, on_info=None, on_kpi=None, on_progress=None) -> None`
- Aim: Run profile-driven cloud import flow with URL routing and mapping execution.
- Parameters:
  - `config: CloudWorkflowConfig`: runtime setup (credentials, URL source, concurrency, scraper settings).
  - `configuration_provider_create(filepath)`: provider factory for dynamic config file.
  - `container_factory(provider)`: application container factory.
  - `protocol_factory(context, ...)`: callback protocol factory.
  - `on_info(str) | None`: optional progress callback.
  - `on_kpi(dict) | None`: optional end-of-run KPI callback.
  - `on_progress(dict) | None`: optional in-run graph progress callback.
- Returns: `None`.

## Validate YARRRML before runtime

File: `wordlift_sdk/kg_build/yarrrml_validator.py`
- `validate_yarrrml_text(text, *, path="<memory>") -> YarrrmlValidationResult`
- Aim: Static validation of mapping text for parser/runtime-compatibility issues.
- Parameters:
  - `text: str`: mapping content.
  - `path: str`: label shown in reports.
- Returns: Validation result with issue list and error subset.

- `validate_yarrrml_file(path) -> YarrrmlValidationResult`
- Aim: Static validation for one file.
- Parameters:
  - `path: Path`: local mapping path.
- Returns: Validation result for file.

- `validate_yarrrml_paths(paths) -> list[YarrrmlValidationResult]`
- Aim: Bulk static validation for multiple mappings.
- Parameters:
  - `paths: Iterable[Path]`: mapping paths.
- Returns: Ordered list of validation results.

## Generate structured data from a single URL

File: `wordlift_sdk/structured_data/orchestrator.py`
- `CreateWorkflow.run(request, log) -> StructuredDataResult`
- Aim: End-to-end single-page generation (render + agent + mapping + validation + file output).
- Parameters:
  - `request: CreateRequest` with key fields:
  - required: `url`, `target_type`, `output_dir`, `base_name`.
  - optional output paths: `jsonld_path`, `yarrml_path`.
  - auth: `api_key`, `base_url`, `ssl_ca_cert`.
  - quality/debug: `quality_check`, `debug`, `validate`, `verbose`.
  - rendering: `headed`, `timeout_ms`, `wait_until`.
  - prompt/cleanup: `max_retries`, `max_xhtml_chars`, `max_text_node_chars`, `max_nesting_depth`.
  - `log: Callable[[str], None]`: progress callback.
- Returns: JSON-LD and YARRRML payloads + output file names.

File: `wordlift_sdk/structured_data/orchestrator.py`
- `resolve_api_key_from_context(ctx_config, env_key="WORDLIFT_KEY") -> str | None`
- Aim: Resolve API key from runtime config first, environment fallback second.
- Parameters:
  - `ctx_config: object | None`: configuration object exposing `.get(...)`.
  - `env_key: str`: environment variable key for fallback.
- Returns: API key or `None`.

File: `wordlift_sdk/structured_data/models.py`
- `CreateRequest`
- Aim: Input contract for `CreateWorkflow.run`.
- `GenerateRequest`
- Aim: Input contract for `GenerateWorkflow.run`.

## Low-level structured data pipeline controls

File: `wordlift_sdk/structured_data/materialization.py`
- `MaterializationPipeline.normalize(yarrrml, url, xhtml_path, response=None) -> tuple[str, list[dict]]`
- Aim: Normalize mapping text and resolve callback/runtime placeholders before materialization.
- Parameters:
  - `yarrrml: str`, `url: str`, `xhtml_path: Path`, `response: object | None`.
- Returns: normalized YARRRML + extracted mapping descriptors.

- `MaterializationPipeline.materialize(normalized_yarrrml, xhtml_path, workdir, url=None, response=None, strict_url_token=False) -> dict`
- Aim: Execute normalized YARRRML and produce raw JSON-LD.
- Parameters:
  - `normalized_yarrrml: str`, `xhtml_path: Path`, `workdir: Path`.
  - `url: str | None`, `response: object | None`.
  - `strict_url_token: bool`: fail if `__URL__` cannot be resolved.
- Returns: raw materialized JSON-LD payload.

- `MaterializationPipeline.postprocess(jsonld_raw, mappings, cleaned_xhtml, dataset_uri, url) -> dict`
- Aim: Normalize/finalize JSON-LD after materialization.
- Parameters:
  - `jsonld_raw: dict`, `mappings: list[dict]`, `cleaned_xhtml: str`, `dataset_uri: str`, `url: str`.
- Returns: final JSON-LD dict.

- `MaterializationPipeline.run(yarrrml, url, cleaned_xhtml, dataset_uri, xhtml_path, workdir, response=None, strict_url_token=False) -> tuple[dict, list[dict]]`
- Aim: One-call normalize + materialize + postprocess.
- Parameters: combination of the three methods above.
- Returns: final JSON-LD and mapping descriptors.

File: `wordlift_sdk/structured_data/structured_data_engine.py`
- `StructuredDataEngine.get_dataset_uri(api_key, base_url=..., ssl_ca_cert=None) -> str`
- Aim: Resolve dataset URI from account API.
- Parameters:
  - `api_key: str`, `base_url: str`, `ssl_ca_cert: str | None`.
- Returns: dataset URI.

- `StructuredDataEngine.get_dataset_uri_async(api_key, base_url=..., ssl_ca_cert=None) -> str`
- Aim: Async variant of dataset URI resolution.

- `StructuredDataEngine.normalize_yarrrml_mappings(yarrrml, url, xhtml_path, response=None) -> tuple[str, list[dict]]`
- Aim: Wrapper around mapping normalization.

- `StructuredDataEngine.materialize_yarrrml_jsonld(yarrrml, xhtml_path, workdir, response=None, url=None, strict_url_token=False) -> dict | list`
- Aim: Wrapper around mapping execution to JSON-LD.

- `StructuredDataEngine.postprocess_jsonld(jsonld_raw, mappings, xhtml, dataset_uri, url) -> dict`
- Aim: Wrapper around JSON-LD postprocessing.

- `StructuredDataEngine.make_reusable_yarrrml(yarrml, url, source_placeholder="__XHTML__") -> str`
- Aim: Convert page-specific mapping into reusable mapping by replacing source URL/XHTML tokens.

- `StructuredDataEngine.ensure_no_blank_nodes(graph) -> None`
- Aim: Enforce no-blank-node output requirement (raises if found).

- `StructuredDataEngine.build_output_basename(url, default="page") -> str`
- Aim: Deterministic output basename for a URL.

- `StructuredDataEngine.shape_specs_for_type(type_name) -> list[str]`
- Aim: Return shape spec set used for validation.

## Validate produced JSON-LD / RDF

File: `wordlift_sdk/validation/shacl.py`
- `validate_jsonld_from_url(url, shape_specs=None, render_options=None) -> ValidationResult`
- Aim: Render a URL, extract JSON-LD scripts, and validate with SHACL shapes.
- Parameters:
  - `url: str`: page URL.
  - `shape_specs: Iterable[str] | None`: bundled shape names or `.ttl` paths.
  - `render_options: RenderOptions | None`: rendering override.
- Returns: SHACL validation result with report graph/text and warning count.

- `validate_file(input_file, shape_specs=None) -> ValidationResult`
- Aim: Validate existing RDF/JSON-LD file (or URL) with SHACL.
- Parameters:
  - `input_file: str`: local file path or HTTP URL.
  - `shape_specs: Iterable[str] | None`: shape selection.
- Returns: SHACL validation result.

- `list_shape_names() -> list[str]`
- Aim: Enumerate bundled shape resources.
- Returns: sorted shape filenames.

## Render and clean pages for mapping workflows

File: `wordlift_sdk/render/__init__.py`
- `render_html(options: RenderOptions) -> RenderedPage`
- Aim: Render a URL to HTML/XHTML via Playwright.
- Parameters:
  - `options.url: str` required.
  - `options.headless: bool`, `options.timeout_ms: int`, `options.wait_until: str`.
  - `options.locale: str`, `options.user_agent: str | None`.
  - `options.viewport_width: int`, `options.viewport_height: int`.
  - `options.ignore_https_errors: bool`.
- Returns: rendered payload (`html`, `xhtml`, response metadata).

- `clean_xhtml(xhtml: str, options: CleanupOptions) -> str`
- Aim: sanitize/truncate XHTML for mapping/agent workflows.
- Parameters:
  - `xhtml: str`: raw XHTML.
  - `options.max_xhtml_chars: int`, `options.max_text_node_chars: int`, `options.remove_tags: tuple[str, ...]`.
- Returns: cleaned XHTML string.

## Run import workflows

File: `wordlift_sdk/main.py`
- `run_kg_import_workflow() -> None`
- Aim: Execute default import workflow from configured source.
- Parameters: none (reads runtime configuration).
- Returns: `None` (async function).

File: `wordlift_sdk/kg_build/cloud_flow.py`
- `CloudWorkflowConfig(...)`
- Aim: Configuration contract for `run_cloud_workflow`.
- Parameters:
  - required: `wordlift_key: str`.
  - conditional: `sheets_service_account_json: str | None` (required only for sheets source mode).
  - source (exactly one mode): `urls: Sequence[str] | None`, or `sitemap_url: str | None` (+ optional `sitemap_url_pattern: str | None`), or `sheets_url: str | None` + `sheets_name: str | None`.
  - execution: `overwrite: bool`, `concurrency: int`, `ingest_loader: str`, `ingest_timeout_ms: int | None`, `playwright_wait_until: str | None`.
  - default Playwright ingestion settings emitted by cloud flow: `INGEST_TIMEOUT_MS = 30000`, `PLAYWRIGHT_WAIT_UNTIL = "domcontentloaded"`.
  - timeout precedence in cloud flow: typed `ingest_timeout_ms`, then compatibility keys in `extra_settings` (`INGEST_TIMEOUT_MS` / `WEB_PAGE_IMPORT_TIMEOUT`), then SDK default `30000`.
  - optional: `extra_settings`, `debug`, `debug_profile_name`.

- `get_debug_output_dir(config, root_dir=None) -> Path | None`
- Aim: Resolve debug output folder for cloud workflow.
- Parameters:
  - `config: CloudWorkflowConfig`, `root_dir: Path | None`.
- Returns: debug path or `None` when debug is off.

- `CloudWorkflowConfigError`
- Aim: Typed config validation error for cloud workflow setup.

## Build authenticated API client configuration

File: `wordlift_sdk/client/client_configuration_factory.py`
- `ClientConfigurationFactory(key, api_url="https://api.wordlift.io", ssl_ca_cert=None).create() -> wordlift_client.Configuration`
- Aim: Build authenticated API client configuration with SSL verification.
- Parameters:
  - `key: str`: API key.
  - `api_url: str`: API base URL.
  - `ssl_ca_cert: str | None`: custom CA bundle path.
- Returns: configured `wordlift_client.Configuration`.

## GraphQL/query helpers

File: `wordlift_sdk/graphql/client/client.py`
- `GraphQlClient.run(graphql, variables=None) -> list[dict[str, Any]]`
- Aim: Execute one bundled GraphQL query against `entities`.
- Parameters:
  - `graphql: str`: one of `entities_top_query`, `entities_url_id`, `entities_url_iri`, `entities_url_iri_with_source_equal_to_web_page_import`.
  - `variables: dict | None`: query variables.
- Returns: list of entity records.

File: `wordlift_sdk/graphql/client/factory.py`
- `GraphQlClientFactory(key, api_url="https://api.wordlift.io/graphql")`
- Aim: Factory for low-level and wrapped GraphQL clients.
- Parameters:
  - `key: str`, `api_url: str`.

- `create() -> GraphQlClient`
- Aim: Build wrapped query client (`GraphQlClient.run`).

- `create_provider() -> GqlClientProvider`
- Aim: Build session provider for advanced GraphQL usage.

- `create_gql_client() -> gql.Client`
- Aim: Build raw `gql` client for custom queries.

File: `wordlift_sdk/graphql/utils/query/entity_with_top_query.py`
- `entity_with_top_query_factory(key) -> Callable[[str], Awaitable[EntityTopQuery | None]]`
- Aim: Build URL lookup helper returning top-query enriched entity.
- Parameters:
  - `key: str`: API key.
- Returns: async callable accepting one URL.

## Entity-store URL lookup helpers

File: `wordlift_sdk/kg/entity_store.py`
- `EntityStore.url_id(url_list=None) -> AsyncGenerator[Entity, None]`
- Aim: stream URL->ID matches.
- Parameters:
  - `url_list: list[str] | None`: URLs to query.
- Returns: async stream of `Entity`.

- `EntityStore.url_iri(url_list=None) -> AsyncGenerator[Entity, None]`
- Aim: stream URL->IRI matches.

- `EntityStore.url_id_as_dataframe(url_list=None) -> DataFrame`
- Aim: dataframe projection for URL->ID.

- `EntityStore.url_iri_as_dataframe(url_list=None) -> DataFrame`
- Aim: dataframe projection for URL->IRI.

File: `wordlift_sdk/kg/entity_store_factory.py`
- `EntityStoreFactory(gql_client)`
- Aim: dependency-injected builder for `EntityStore`.
- Parameters:
  - `gql_client`: initialized `gql.Client`.

- `EntityStoreFactory.create() -> EntityStore`
- Aim: create store instance.

File: `wordlift_sdk/utils/create_dataframe_of_url_iri.py`
- `create_dataframe_of_url_iri(key, url_list) -> DataFrame`
- Aim: convenience async helper for URL->IRI dataframe.
- Parameters:
  - `key: str`, `url_list: list[str]`.

## URL source and workflow composition primitives

File: `wordlift_sdk/container/application_container.py`
- `ApplicationContainer.create_kg_import_workflow() -> KgImportWorkflow`
- Aim: assemble import workflow from active config.

- `ApplicationContainer.create_url_source() -> UrlSource`
- Aim: resolve configured source (`SITEMAP_URL`, `SHEETS_*`, or `URLS`).

- `ApplicationContainer.create_new_or_changed_source() -> UrlSource`
- Aim: wrap URL source with change detection (`OVERWRITE` aware).

File: `wordlift_sdk/url_source/url_source.py`
- `Url(value, iri=None, date_modified=None)`
- Aim: normalized URL item exchanged across handlers.
- Parameters:
  - `value: str`, `iri: str | None`, `date_modified: datetime | None`.

- `UrlSource.urls() -> AsyncGenerator[Url, None]`
- Aim: abstract protocol for URL iterators.

File: `wordlift_sdk/url_source/list_url_source.py`
- `ListUrlSource(urls)`
- Aim: URL source from in-memory URL list.
- Parameters:
  - `urls: list[str]`.

File: `wordlift_sdk/url_source/sitemap_url_source.py`
- `SitemapUrlSource(sitemap_url, pattern=None)`
- Aim: URL source from XML sitemap.
- Parameters:
  - `sitemap_url: str`, `pattern: re.Pattern | None`.

File: `wordlift_sdk/url_source/google_sheets_url_source.py`
- `GoogleSheetsUrlSource(creds_or_client, url, sheet)`
- Aim: URL source from Google Sheets `url` column.
- Parameters:
  - `creds_or_client: Credentials | gspread.Client`, `url: str`, `sheet: str`.

## Selection guide

- Need runtime proof that mapping works on a page: `RmlMappingService.apply_mapping`.
- Need fast preflight on mapping quality/compatibility: `validate_yarrrml_file`.
- Need single-page create flow (no pre-authored mapping required): `CreateWorkflow.run`.
- Need mapped output for many pages with existing mapping: `GenerateWorkflow.run`.
- Need production profile+routing execution: `run_cloud_workflow`.

## Task Quickstarts

### 1) Validate mapping text/file first (preflight)

```python
from pathlib import Path
from wordlift_sdk.kg_build import validate_yarrrml_file

result = validate_yarrrml_file(Path("profiles/sample/mappings/default.yarrrml"))
if result.errors:
    for issue in result.errors:
        print(issue.code, issue.line, issue.message)
```

### 2) Run existing mapping over many URLs

```python
from pathlib import Path
from wordlift_sdk.structured_data import GenerateRequest, GenerateWorkflow

request = GenerateRequest(
    input_value="https://example.com/sitemap.xml",
    yarrrml_path=Path("mappings/default.yarrrml"),
    regex=".*",
    output_dir=Path("out"),
    output_format="jsonld",
    concurrency="4",
    api_key="YOUR_WORDLIFT_KEY",
    base_url=None,
    ssl_ca_cert=None,
    headed=False,
    timeout_ms=30000,
    wait_until="networkidle",
    max_xhtml_chars=40000,
    max_text_node_chars=400,
    max_pages=None,
    verbose=True,
)
summary = GenerateWorkflow().run(request, log=print)
print(summary["success"], summary["failed"])
```

### 3) Generate structured data for one URL

```python
from pathlib import Path
from wordlift_sdk.structured_data import CreateRequest, CreateWorkflow

request = CreateRequest(
    url="https://example.com/page",
    target_type="Thing",
    output_dir=Path("out"),
    base_name="page",
    jsonld_path=None,
    yarrml_path=None,
    api_key="YOUR_WORDLIFT_KEY",
    base_url=None,
    ssl_ca_cert=None,
    debug=False,
    headed=False,
    timeout_ms=30000,
    max_retries=2,
    quality_check=False,
    max_xhtml_chars=40000,
    max_text_node_chars=400,
    max_nesting_depth=2,
    verbose=True,
    validate=True,
    wait_until="networkidle",
)
result = CreateWorkflow().run(request, log=print)
print(result.jsonld_filename, result.yarrml_filename)
```

### 4) Validate JSON-LD from a live URL with SHACL

```python
from wordlift_sdk.validation import validate_jsonld_from_url

result = validate_jsonld_from_url(
    "https://example.com/page",
    shape_specs=["google-product-snippet", "schemaorg-grammar"],
)
print(result.conforms, result.warning_count)
```

### 5) GraphQL entity lookup by URL

```python
import asyncio
from wordlift_sdk.graphql.client import GraphQlClientFactory

async def main():
    client = GraphQlClientFactory(key="YOUR_WORDLIFT_KEY").create()
    rows = await client.run("entities_url_iri", {"urls": ["https://example.com/page"]})
    print(rows)

asyncio.run(main())
```

## Operational Behavior Matrix

High-value methods and their operational semantics.

| Method | Sync/Async | Failure mode | Retry behavior | Typical side effects |
|---|---|---|---|---|
| `RmlMappingService.apply_mapping` | async | Returns `None` on failure (logs error) | None | Temp files, mapping reads |
| `GenerateWorkflow.run` | sync | Raises on invalid input/runtime errors | None | Network calls, output writes |
| `CreateWorkflow.run` | sync | Raises on auth/render/agent/materialization errors | Agent loop uses `max_retries` | Network calls, output writes |
| `run_cloud_workflow` | async | Raises config/runtime errors | None | Temp config/credentials files, network calls |
| `validate_yarrrml_file` | sync | Raises on file read failures; issues returned in payload | None | File reads |
| `validate_jsonld_from_url` | sync | Raises on render/parse/validation setup errors | None | Network calls |
| `GraphQlClient.run` | async | Raises GraphQL transport/runtime errors | None | Network calls |
| `entity_with_top_query_factory(...)->fn(url)` | async | Raises after retries exhausted | 5 attempts (`tenacity`) | Network calls |
| `EntityStore.url_id` / `url_iri` | async | Mixed (logs retry errors; stream may stop) | 3 attempts (`tenacity`) | Network calls |

## API Stability Contract

- `stable`: intended public APIs. Breaking behavior/signature changes should align with major-version changes.
- `advanced`: low-level composition APIs. More flexible but may change with fewer compatibility guarantees.
- Rule of thumb:
  - Application/client integrations should prefer `stable` entries in the metadata index.
  - Tooling and internal orchestration can use `advanced` APIs with tighter version pinning.

## Documentation Drift Guard

To keep docs trustworthy for both humans and agents:
- `tests/test_docs_public_entry_points_sync.py` verifies the metadata index references real files and symbols.
- Run as part of the standard suite:
  - `poetry run pytest -q`

## Agent Metadata Index

Machine-readable inventory for agent ingestion.

Schema:
- `id`: stable method identifier.
- `task`: primary job bucket.
- `file`: defining module.
- `signature`: callable signature (or class constructor).
- `sync_async`: `sync` or `async`.
- `side_effects`: high-level runtime effects.
- `raises`: common failure mode (`raises`, `returns_none_on_failure`, or `mixed`).
- `stability`: `stable` (recommended public) or `advanced` (low-level/composition).

```yaml
methods:
  - id: kg_build.rml_mapping.apply_mapping
    task: run_mappings_on_url
    file: wordlift_sdk/kg_build/rml_mapping.py
    signature: RmlMappingService.apply_mapping(html, url, mapping_file_path, xhtml=None, mapping_content=None, response=None) -> Graph | None
    sync_async: async
    side_effects: [network_calls, temp_files]
    raises: returns_none_on_failure
    stability: stable

  - id: structured_data.generate_workflow.run
    task: run_mappings_batch
    file: wordlift_sdk/structured_data/orchestrator.py
    signature: GenerateWorkflow.run(request, log) -> dict[str, object]
    sync_async: sync
    side_effects: [network_calls, filesystem_writes]
    raises: raises
    stability: stable

  - id: kg_build.cloud_flow.run_cloud_workflow
    task: profile_cloud_run
    file: wordlift_sdk/kg_build/cloud_flow.py
    signature: run_cloud_workflow(*, config, configuration_provider_create, container_factory, protocol_factory, on_info=None, on_kpi=None, on_progress=None) -> None
    sync_async: async
    side_effects: [network_calls, filesystem_writes, temp_files]
    raises: raises
    stability: stable

  - id: kg_build.validator.validate_yarrrml_text
    task: validate_yarrrml
    file: wordlift_sdk/kg_build/yarrrml_validator.py
    signature: validate_yarrrml_text(text, *, path="<memory>") -> YarrrmlValidationResult
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: kg_build.validator.validate_yarrrml_file
    task: validate_yarrrml
    file: wordlift_sdk/kg_build/yarrrml_validator.py
    signature: validate_yarrrml_file(path) -> YarrrmlValidationResult
    sync_async: sync
    side_effects: [filesystem_reads]
    raises: raises
    stability: stable

  - id: kg_build.validator.validate_yarrrml_paths
    task: validate_yarrrml
    file: wordlift_sdk/kg_build/yarrrml_validator.py
    signature: validate_yarrrml_paths(paths) -> list[YarrrmlValidationResult]
    sync_async: sync
    side_effects: [filesystem_reads]
    raises: raises
    stability: stable

  - id: structured_data.create_workflow.run
    task: generate_single_url
    file: wordlift_sdk/structured_data/orchestrator.py
    signature: CreateWorkflow.run(request, log) -> StructuredDataResult
    sync_async: sync
    side_effects: [network_calls, filesystem_writes]
    raises: raises
    stability: stable

  - id: structured_data.resolve_api_key_from_context
    task: resolve_auth
    file: wordlift_sdk/structured_data/orchestrator.py
    signature: resolve_api_key_from_context(ctx_config, env_key="WORDLIFT_KEY") -> str | None
    sync_async: sync
    side_effects: [env_reads]
    raises: returns_none_on_failure
    stability: stable

  - id: structured_data.materialization.normalize
    task: low_level_materialization
    file: wordlift_sdk/structured_data/materialization.py
    signature: MaterializationPipeline.normalize(yarrrml, url, xhtml_path, response=None) -> tuple[str, list[dict]]
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: advanced

  - id: structured_data.materialization.materialize
    task: low_level_materialization
    file: wordlift_sdk/structured_data/materialization.py
    signature: MaterializationPipeline.materialize(normalized_yarrrml, xhtml_path, workdir, url=None, response=None, strict_url_token=False) -> dict
    sync_async: sync
    side_effects: [filesystem_writes]
    raises: raises
    stability: advanced

  - id: structured_data.materialization.postprocess
    task: low_level_materialization
    file: wordlift_sdk/structured_data/materialization.py
    signature: MaterializationPipeline.postprocess(jsonld_raw, mappings, cleaned_xhtml, dataset_uri, url) -> dict
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: advanced

  - id: structured_data.materialization.run
    task: low_level_materialization
    file: wordlift_sdk/structured_data/materialization.py
    signature: MaterializationPipeline.run(yarrrml, url, cleaned_xhtml, dataset_uri, xhtml_path, workdir, response=None, strict_url_token=False) -> tuple[dict, list[dict]]
    sync_async: sync
    side_effects: [filesystem_writes]
    raises: raises
    stability: advanced

  - id: structured_data.engine.get_dataset_uri
    task: dataset_resolution
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.get_dataset_uri(api_key, base_url=..., ssl_ca_cert=None) -> str
    sync_async: sync
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: structured_data.engine.get_dataset_uri_async
    task: dataset_resolution
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.get_dataset_uri_async(api_key, base_url=..., ssl_ca_cert=None) -> str
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: structured_data.engine.normalize_yarrrml_mappings
    task: low_level_materialization
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.normalize_yarrrml_mappings(yarrrml, url, xhtml_path, response=None) -> tuple[str, list[dict]]
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: advanced

  - id: structured_data.engine.materialize_yarrrml_jsonld
    task: low_level_materialization
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.materialize_yarrrml_jsonld(yarrrml, xhtml_path, workdir, response=None, url=None, strict_url_token=False) -> dict | list
    sync_async: sync
    side_effects: [filesystem_writes]
    raises: raises
    stability: advanced

  - id: structured_data.engine.postprocess_jsonld
    task: low_level_materialization
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.postprocess_jsonld(jsonld_raw, mappings, xhtml, dataset_uri, url) -> dict
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: advanced

  - id: structured_data.engine.make_reusable_yarrrml
    task: mapping_reusability
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.make_reusable_yarrrml(yarrml, url, source_placeholder="__XHTML__") -> str
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: structured_data.engine.ensure_no_blank_nodes
    task: rdf_quality_guard
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.ensure_no_blank_nodes(graph) -> None
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: advanced

  - id: structured_data.engine.build_output_basename
    task: naming
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.build_output_basename(url, default="page") -> str
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: structured_data.engine.shape_specs_for_type
    task: shape_selection
    file: wordlift_sdk/structured_data/structured_data_engine.py
    signature: StructuredDataEngine.shape_specs_for_type(type_name) -> list[str]
    sync_async: sync
    side_effects: [filesystem_reads]
    raises: raises
    stability: stable

  - id: validation.validate_jsonld_from_url
    task: shacl_validate_rendered_url
    file: wordlift_sdk/validation/shacl.py
    signature: validate_jsonld_from_url(url, shape_specs=None, render_options=None) -> ValidationResult
    sync_async: sync
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: validation.validate_file
    task: shacl_validate_artifact
    file: wordlift_sdk/validation/shacl.py
    signature: validate_file(input_file, shape_specs=None) -> ValidationResult
    sync_async: sync
    side_effects: [filesystem_reads, network_calls]
    raises: raises
    stability: stable

  - id: validation.list_shape_names
    task: shape_discovery
    file: wordlift_sdk/validation/shacl.py
    signature: list_shape_names() -> list[str]
    sync_async: sync
    side_effects: [filesystem_reads]
    raises: raises
    stability: stable

  - id: render.render_html
    task: page_rendering
    file: wordlift_sdk/render/__init__.py
    signature: render_html(options) -> RenderedPage
    sync_async: sync
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: render.clean_xhtml
    task: xhtml_cleanup
    file: wordlift_sdk/render/__init__.py
    signature: clean_xhtml(xhtml, options) -> str
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: main.run_kg_import_workflow
    task: default_import_workflow
    file: wordlift_sdk/main.py
    signature: run_kg_import_workflow() -> None
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: kg_build.cloud_flow.get_debug_output_dir
    task: cloud_debug_path
    file: wordlift_sdk/kg_build/cloud_flow.py
    signature: get_debug_output_dir(config, root_dir=None) -> Path | None
    sync_async: sync
    side_effects: [filesystem_writes]
    raises: raises
    stability: stable

  - id: client.client_configuration_factory.create
    task: client_bootstrap
    file: wordlift_sdk/client/client_configuration_factory.py
    signature: ClientConfigurationFactory(...).create() -> wordlift_client.Configuration
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: graphql.client.run
    task: graphql_query
    file: wordlift_sdk/graphql/client/client.py
    signature: GraphQlClient.run(graphql, variables=None) -> list[dict[str, Any]]
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: graphql.factory.create
    task: graphql_client_factory
    file: wordlift_sdk/graphql/client/factory.py
    signature: GraphQlClientFactory.create() -> GraphQlClient
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: graphql.factory.create_provider
    task: graphql_client_factory
    file: wordlift_sdk/graphql/client/factory.py
    signature: GraphQlClientFactory.create_provider() -> GqlClientProvider
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: graphql.factory.create_gql_client
    task: graphql_client_factory
    file: wordlift_sdk/graphql/client/factory.py
    signature: GraphQlClientFactory.create_gql_client() -> gql.Client
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: graphql.utils.entity_with_top_query_factory
    task: graphql_query_helper
    file: wordlift_sdk/graphql/utils/query/entity_with_top_query.py
    signature: entity_with_top_query_factory(key) -> Callable[[str], Awaitable[EntityTopQuery | None]]
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: kg.entity_store.url_id
    task: entity_lookup
    file: wordlift_sdk/kg/entity_store.py
    signature: EntityStore.url_id(url_list=None) -> AsyncGenerator[Entity, None]
    sync_async: async
    side_effects: [network_calls]
    raises: mixed
    stability: stable

  - id: kg.entity_store.url_iri
    task: entity_lookup
    file: wordlift_sdk/kg/entity_store.py
    signature: EntityStore.url_iri(url_list=None) -> AsyncGenerator[Entity, None]
    sync_async: async
    side_effects: [network_calls]
    raises: mixed
    stability: stable

  - id: kg.entity_store.url_id_as_dataframe
    task: entity_lookup
    file: wordlift_sdk/kg/entity_store.py
    signature: EntityStore.url_id_as_dataframe(url_list=None) -> DataFrame
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: kg.entity_store.url_iri_as_dataframe
    task: entity_lookup
    file: wordlift_sdk/kg/entity_store.py
    signature: EntityStore.url_iri_as_dataframe(url_list=None) -> DataFrame
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: kg.entity_store_factory.create
    task: entity_store_factory
    file: wordlift_sdk/kg/entity_store_factory.py
    signature: EntityStoreFactory.create() -> EntityStore
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: utils.create_dataframe_of_url_iri
    task: entity_lookup
    file: wordlift_sdk/utils/create_dataframe_of_url_iri.py
    signature: create_dataframe_of_url_iri(key, url_list) -> DataFrame
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: container.create_kg_import_workflow
    task: workflow_composition
    file: wordlift_sdk/container/application_container.py
    signature: ApplicationContainer.create_kg_import_workflow() -> KgImportWorkflow
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: advanced

  - id: container.create_url_source
    task: workflow_composition
    file: wordlift_sdk/container/application_container.py
    signature: ApplicationContainer.create_url_source() -> UrlSource
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: advanced

  - id: container.create_new_or_changed_source
    task: workflow_composition
    file: wordlift_sdk/container/application_container.py
    signature: ApplicationContainer.create_new_or_changed_source() -> UrlSource
    sync_async: async
    side_effects: [network_calls]
    raises: raises
    stability: advanced

  - id: url_source.url_dataclass
    task: url_item_model
    file: wordlift_sdk/url_source/url_source.py
    signature: Url(value, iri=None, date_modified=None)
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: url_source.list
    task: url_sources
    file: wordlift_sdk/url_source/list_url_source.py
    signature: ListUrlSource(urls)
    sync_async: sync
    side_effects: [none]
    raises: raises
    stability: stable

  - id: url_source.sitemap
    task: url_sources
    file: wordlift_sdk/url_source/sitemap_url_source.py
    signature: SitemapUrlSource(sitemap_url, pattern=None)
    sync_async: sync
    side_effects: [network_calls]
    raises: raises
    stability: stable

  - id: url_source.google_sheets
    task: url_sources
    file: wordlift_sdk/url_source/google_sheets_url_source.py
    signature: GoogleSheetsUrlSource(creds_or_client, url, sheet)
    sync_async: sync
    side_effects: [network_calls]
    raises: raises
    stability: stable
```

# Structured Data

This module provides the structured data pipeline used to render pages, generate YARRRML mappings and JSON-LD, and validate output.

## Core classes

### StructuredDataEngine
Facade that wires dataset resolution, schema guidance, YARRRML handling, and agent generation.

Key methods:
- `get_dataset_uri(api_key, base_url=DEFAULT_BASE_URL)`
- `shape_specs_for_type(type_name)`
- `generate_from_agent(...)`

### AgentGenerator
Calls the agent API to generate YARRRML mappings and JSON-LD. Used by `CreateWorkflow`.

### DatasetResolver
Builds API clients and resolves dataset URIs.

Key methods:
- `get_dataset_uri(api_key, base_url=DEFAULT_BASE_URL)`
- `get_dataset_uri_async(api_key, base_url=DEFAULT_BASE_URL)`

### SchemaGuide
Maps schema.org types to available SHACL shapes and helps select relevant shape specs.

### YarrrmlPipeline
Generic YARRRML helpers for structural normalization, materialization, and postprocessing.

Key methods:
- `normalize_mappings(yarrrml, url, xhtml_path, response=None)`
- `materialize_jsonld(yarrrml, xhtml_path, workdir, response=None, url=None, strict_url_token=False)`
- `postprocess_jsonld(jsonld_raw, mappings, xhtml, dataset_uri, url)`
- `ensure_no_blank_nodes(graph)`

## Pipeline behavior (breaking)

The materialization path is mapping-preserving by default:
- No synthetic remapping to internal `ex:*` structures.
- No implicit coercion to `Review`/`Thing`.
- No review-specific postprocessing (`_dedupe_review_notes`, review URL/author/rating injections).
- YARRRML is executed directly by `morph-kgc` native YARRRML support (no `yarrrml-parser` transpile step and no temporary RML `.ttl` artifact).

### Runtime tokens

Mapping content supports runtime token replacement before direct materialization:
- `__XHTML__`: replaced with callback XHTML local file path.
- `__URL__`: replaced from `response.web_page.url` first, then explicit `url` argument.
- `__ID__`: replaced from `response.id`.

`strict_url_token=True` fails if `__URL__` is unresolved.
Default non-strict policy logs a warning and leaves `__URL__` unchanged.
`__ID__` is always fail-closed when unresolved.

Use `__ID__` in subject/object IRI positions to anchor generated triples to
the callback/import root entity IRI instead of hardcoded temporary page IRIs.

### Error model

Materialization raises explicit runtime errors for:
- malformed YARRRML mappings
- unsupported XPath/function constructs
- unresolved `__URL__` when strict mode is enabled
- unresolved `__ID__` when the token appears in mapping content

Compatibility note: `morph-kgc` native YARRRML handling may differ from legacy JS parser behavior in edge mappings; update mappings to align with `morph-kgc` semantics.

When XHTML input is produced by `wordlift_sdk.utils.html_converter.HtmlConverter`,
undeclared namespace prefixes are sanitized (`prefix:tag` -> `tag`; undeclared
prefixed attributes dropped) so XML/XPath materialization does not fail with
`unbound prefix` parser errors.
The converter also strips XML-invalid comment/PI nodes and validates serialized
XHTML with `ElementTree.fromstring()` using a strict fallback sanitation pass.

## Workflows

### CreateWorkflow
End-to-end workflow for a single URL.

Inputs (see `CreateRequest`):
- `url`, `target_type`, `output_dir`, `api_key`, `base_url`, `debug`, `validate`, rendering and prompt limits

Outputs:
- JSON-LD and YARRRML files
- `StructuredDataResult` with filenames and in-memory payloads

### GenerateWorkflow
Batch generation workflow using an existing YARRRML mapping and a URL source.

Inputs (see `GenerateRequest`):
- `input_value`, `yarrrml_path`, `output_dir`, `output_format`, `concurrency`, `api_key`, `base_url`

Outputs:
- Summary dict with counts and output location

### RenderPipeline
Renders a page with Playwright and cleans XHTML for prompt usage.

### ValidationService
Validates JSON-LD output with SHACL shapes.

## Request/response models

- `CreateRequest`
- `GenerateRequest`
- `StructuredDataOptions`
- `StructuredDataResult`

## Typical usage

```python
from pathlib import Path
from wordlift_sdk.structured_data import CreateRequest, CreateWorkflow

request = CreateRequest(
    url="https://example.com",
    target_type="Thing",
    output_dir=Path("out"),
    base_name="structured-data",
    jsonld_path=None,
    yarrml_path=None,
    api_key="YOUR_KEY",
    base_url=None,
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
print(result.jsonld_filename)
```

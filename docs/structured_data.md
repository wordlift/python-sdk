# Structured Data

This module provides the structured data pipeline used to render pages, generate YARRRML mappings and JSON-LD, and validate output.

## Core classes

### StructuredDataEngine
Facade that wires dataset resolution, schema guidance, YARRRML handling, and agent generation.

Key methods:
- `get_dataset_uri(api_key, base_url=DEFAULT_BASE_URL)`
- `shape_specs_for_type(type_name)`
- `make_reusable_yarrrml(yarrrml, url)`
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
Normalizes YARRRML mappings, materializes JSON-LD, and applies post-processing.

Key methods:
- `normalize_mappings(yarrrml)`
- `materialize_jsonld(yarrrml, workdir)`
- `postprocess_jsonld(jsonld, dataset_uri)`
- `make_reusable_yarrrml(yarrrml, url)`

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

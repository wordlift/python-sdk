# Validation

SHACL validation utilities and bundled shape files for Google rich results and schema.org checks.

## Core APIs

### validate_file
Validate a JSON-LD/Turtle/N-Triples file or URL against bundled or custom shapes.

```python
from wordlift_sdk.validation.shacl import validate_file

result = validate_file("out/structured-data.jsonld", shape_specs=["google-article"])
print(result.conforms)
print(result.report_text)
```

### ValidationResult
Returned by `validate_file`:
- `conforms` (bool)
- `report_text` (str)
- `report_graph` (rdflib.Graph)
- `data_graph` (rdflib.Graph)
- `shape_source_map` (dict)
- `warning_count` (int)

### list_shape_names
Returns the list of bundled `.ttl` shapes in `wordlift_sdk.validation.shacls`.

### resolve_shape_specs
Build a deterministic shape set from:
- bundled allowlist (`builtin_shapes`)
- bundled denylist (`exclude_builtin_shapes`)
- extra local/remote shapes (`extra_shapes`)

```python
from wordlift_sdk.validation.shacl import resolve_shape_specs, validate_file

shape_specs = resolve_shape_specs(
    builtin_shapes=["google-article"],
    exclude_builtin_shapes=["schemaorg-grammar"],
    extra_shapes=["./custom-shape.ttl", "https://example.com/custom-shape.ttl"],
)
result = validate_file("out/structured-data.jsonld", shape_specs=shape_specs)
```

### Validation issues
`extract_validation_issues(result)` maps SHACL report nodes into stable issue objects:
- `level` (`warning|error`)
- `severity` (raw SHACL severity IRI)
- `focus_node`
- `result_path`
- `rule_id` (source shape identifier)
- `rule_set` (shape file/source label)
- `message`

`filter_validation_issues(issues, level="warning"|"error")` filters issue output.

## Bundled shapes

Shape files are shipped in `wordlift_sdk/validation/shacls/`. You can reference them by name
(e.g., `google-article`) or by path to a local `.ttl` file.

## SDK composition pattern

The SDK is API-first. Host applications can build their own CLI/UX layer on top
of these helpers:

```python
from wordlift_sdk.validation.shacl import (
    resolve_shape_specs,
    validate_file,
    extract_validation_issues,
    filter_validation_issues,
)

shape_specs = resolve_shape_specs(
    builtin_shapes=["google-article"],
    exclude_builtin_shapes=["schemaorg-grammar"],
    extra_shapes=["./custom-shape.ttl", "https://example.com/custom-shape.ttl"],
)
result = validate_file("out/page.jsonld", shape_specs=shape_specs)
issues = extract_validation_issues(result)
errors_only = filter_validation_issues(issues, level="error")
```

## Generator

`wordlift_sdk.validation.generator` contains the helper scripts used to generate the bundled
SHACL files from the schema.org grammar and Google Search Gallery feature pages.
Google-table parsing supports both property-level "one of" alternatives and explicit
option branches (`Option A` / `Option B`) where each branch can require multiple properties.

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

By default, bundled-shape resolution excludes `google-image-license-metadata`.
To validate image license metadata, opt in explicitly with
`shape_specs=["google-image-license-metadata"]` or via
`resolve_shape_specs(builtin_shapes=["google-image-license-metadata"])`.

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
Required rows that explicitly document a supported fallback (for example, `url` when
`contentUrl` is not provided) are emitted as `sh:or` alternatives.
Recommended-table "choose either ... or ..." alternatives are emitted as warning-level
`sh:or` constraints (including scoped/nested shapes; warn only when none of
the alternatives is present).
Paragraph/list guidance that uses "one of the following values" is treated as enum/value
documentation and is not emitted as property-level `sh:or`.
Required sections with conditional language (for example "required when" / "required if")
are emitted as warnings to avoid unconditional constraints for context-dependent rules.
Type-context extraction for Google tables is constrained to explicit type-definition
paragraphs and scoped plain headings (for example `Quiz`, `Question`, `DataFeed entity`)
so example markup snippets do not create unrelated target-class shapes.

Search Gallery sample fixtures are stored under `tests/fixtures/search_gallery/` and can be
refreshed with `python tests/tools/extract_search_gallery_samples.py`.
Conformance baselines and expected non-conforming samples are tracked in:
- `tests/fixtures/search_gallery/baseline_conformance.json`
- `tests/fixtures/search_gallery/expectations.json`

Use `python tests/tools/search_gallery_conformance_diff.py` to print per-page
baseline vs current conformance deltas and fail on regressions.

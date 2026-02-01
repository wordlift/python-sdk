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

## Bundled shapes

Shape files are shipped in `wordlift_sdk/validation/shacls/`. You can reference them by name
(e.g., `google-article`) or by path to a local `.ttl` file.

## Generator

`wordlift_sdk.validation.generator` contains the helper scripts used to generate the bundled
SHACL files from the schema.org grammar.

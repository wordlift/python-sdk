# Structured Data Materialization Spec

## Runtime Placeholder Tokens

The YARRRML materialization pipeline supports reserved runtime placeholders:

- `__XHTML__`: local XHTML source path injected at runtime.
- `__URL__`: canonical page URL injected at runtime.
- `__ID__`: callback/import entity IRI injected at runtime.

## Resolution Rules

`__URL__` resolution order:
1. `response.web_page.url`
2. explicit `url` argument

`__ID__` resolution source:
1. `response.id`

## Failure Behavior

- `__URL__`: non-strict mode logs a warning and keeps token unchanged; strict mode
  (`strict_url_token=True`) raises a runtime error.
- `__ID__`: always fail-closed. If token is present and unresolved, the
  pipeline raises a runtime error.

No fallback to synthetic/hardcoded page IRIs is allowed for `__ID__`.

## Scope of Replacement

Token replacement happens before materialization and is global across mapping
content. `__ID__` is therefore supported in any IRI position, including:

- subject `s:` entries
- object IRI terms in `po` blocks

## XHTML Namespace Safety

`HtmlConverter` sanitizes XHTML source before materialization to keep XML parsing
safe for `morph-kgc` XPath sources:

- undeclared prefixed element names are rewritten to their local name
- undeclared prefixed attributes are removed
- declared prefixes and reserved `xml:*` attributes are preserved
- XML-invalid comments and processing instructions are removed
- serialized XHTML is validated with `xml.etree.ElementTree.fromstring()`
- on parse failure, converter runs a stricter fallback sanitation pass and
  raises with precise line/column context if still invalid

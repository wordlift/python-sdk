# Validation Specs

## Google Search Gallery SHACLs

When a Google Search Gallery feature includes container types (for example
`ItemList`, `BreadcrumbList`, `QAPage`, `FAQPage`, `Quiz`, `ProfilePage`, `Product`,
`Recipe`, `Course`, `Review`) and their contained types (`ListItem`, `Question`,
`Answer`, `Comment`, `Offer`, `AggregateOffer`, `HowToStep`, `Person`, `Organization`, `Rating`,
`AggregateRating`, `Review`, `ItemList`), the generator scopes contained
constraints under the container properties instead of targeting the contained
types globally. This prevents list-, Q&A-, and product/profile-specific rules from
applying to unrelated nodes.

The generator also captures "one of" requirements expressed in prose lists
(for example, Product snippets requiring `review` or `aggregateRating` or
`offers`) and emits `sh:or` constraints so any listed property satisfies the
requirement.

For Product snippets, `offers` supports either an `Offer` shape or an
`AggregateOffer` shape.

When a required property row includes alternatives (for example,
`price or priceSpecification.price`), the generator treats the row as a
`sh:or` group so either property satisfies the requirement.

Schema.org grammar checks intentionally allow URL and text literals for every
property (in addition to the documented range types).

## JSON-LD validation from URLs

The validation module can render a URL with Playwright, extract all
`application/ld+json` fragments, flatten them into a single list of JSON-LD
nodes, and pass them through the SHACL validation pipeline.

Playwright is a required dependency for URL rendering. Install browser binaries
with `playwright install` after the Python dependencies are installed.

## Validation API composition contract

Host tooling can validate one or more file/URL inputs via SDK APIs with
deterministic shape composition:

- Built-in allowlist mode: `resolve_shape_specs(builtin_shapes=[...])`.
- Built-in exclusion mode: `resolve_shape_specs(exclude_builtin_shapes=[...])`.
- Extra local/remote SHACL overlays: `resolve_shape_specs(extra_shapes=[...])`.

Shape composition order:
1. If `builtin_shapes` is set, only listed bundled shapes are selected.
2. Otherwise, all bundled shapes are selected.
3. `exclude_builtin_shapes` removes bundled shapes from the selected set.
4. `extra_shapes` values are appended as additional shape sources.

Issue output model uses normalized levels:
- `error`: SHACL `Violation`
- `warning`: SHACL `Warning` and `Info`

Issue fields are:
- `level`
- `severity` (raw SHACL severity IRI)
- `focus_node`
- `result_path`
- `rule_id` (SHACL source shape identifier)
- `rule_set` (shape source label, when resolvable)
- `message`

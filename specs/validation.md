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
Rows with explicit fallback wording (for example, "supports `url` if you don't
include `contentUrl`") are also modeled as `sh:or` alternatives.
Recommended-table alternatives phrased as "choose either ... or ..." are modeled
as warning-level `sh:or` constraints, including scoped/nested type constraints.
Paragraph/list text that says "one of the following values" is treated as value
guidance and must not be converted into property-level `sh:or` alternatives.

Required tables introduced by conditional prose (for example, "required when...",
"required if...", "only required if...") are lowered to warning constraints to
avoid unconditional validation failures for conditional sections.

Google-type context assignment for table sections is derived from explicit
type-definition statements and scoped plain headings, not arbitrary schema links
found in markup examples.

Search Gallery quality gates:
- Fixture extraction output lives under `tests/fixtures/search_gallery/`.
- Baseline conformance by page is stored in
  `tests/fixtures/search_gallery/baseline_conformance.json`.
- Known non-conforming sample IDs are tracked in
  `tests/fixtures/search_gallery/expectations.json`.
- CI compares current fixture conformance to baseline and fails on regressions.

Schema.org grammar checks intentionally allow URL and text literals for every
property (in addition to the documented range types).

Schema.org properties with documented `domainIncludes` values emit warning-level
domain constraints. A property is accepted when any declared Schema.org type is
the documented domain or one of its standard subclasses. Multi-typed nodes use
union semantics, untyped nodes and external predicates are not domain-checked,
and each incompatible subject/property pair produces one deterministic warning.
The grammar and normalized direct-subclass ontology must be regenerated from the
same downloaded Schema.org graph so they remain version-aligned.

## JSON-LD validation from URLs

The validation module can render a URL with Playwright, extract all
`application/ld+json` fragments, flatten them into a single list of JSON-LD
nodes, and pass them through the SHACL validation pipeline.

Playwright is a required dependency for URL rendering. Install browser binaries
with `playwright install` after the Python dependencies are installed.

All Playwright URL rendering disables service workers and aborts direct requests
to the standard Google Analytics measurement host families enumerated in the
render documentation before navigation traffic can leave the browser. Google
Tag Manager and advertising endpoints remain available. The policy also applies
to frames and popup pages.

## Validation API composition contract

Host tooling can validate one or more file/URL inputs via SDK APIs with
deterministic shape composition:

- Built-in allowlist mode: `resolve_shape_specs(builtin_shapes=[...])`.
- Built-in exclusion mode: `resolve_shape_specs(exclude_builtin_shapes=[...])`.
- Extra local/remote SHACL overlays: `resolve_shape_specs(extra_shapes=[...])`.

Shape composition order:
1. If `builtin_shapes` is set, only listed bundled shapes are selected.
2. Otherwise, bundled default shapes are selected (currently excluding
   `google-image-license-metadata`, which is opt-in).
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

## Prepared validator contract

The validation layer exposes reusable shape and validator preparation so callers
can avoid reloading SHACL sources and rebuilding pySHACL shape harvest state on
every validation:

- `prepare_shapes(shape_specs)` returns a cached merged shape bundle.
- `PreparedShaclValidator(prepared_shapes)` creates a reusable validator.
- `PreparedShaclValidator.from_shape_specs(shape_specs)` is the convenience
  constructor for the same flow.
- `PreparedShaclValidator.validate_graph(graph, normalize_schema_org=True)`
  validates an in-memory RDF graph and returns a result object with:
  - `conforms`
  - `report_graph`
  - `report_text`
  - `data_graph`
  - `warning_count`

Shape preparation and validator reuse are intended for repeated validation over
many graphs with the same shape set.

## Graph-audit validation performance contract

Graph-audit KPI collection must avoid duplicate SHACL work where possible while
preserving KPI semantics.

Required behavior:

- Rich-snippets classification and schema-compliance reporting must be derivable
  from a shared validation execution path.
- Schema-compliance must support direct validation of prebuilt per-URL graphs
  via `SchemaComplianceKpi.collect_prebuilt(subgraphs_by_url)`.
- Validator/shape initialization must be reusable across repeated calls on the
  same KPI instance.
- Counts-only operation via `SchemaComplianceKpi(..., include_issue_details=False)`
  must preserve warning/error counts while skipping issue-payload construction.

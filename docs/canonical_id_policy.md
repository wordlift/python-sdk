# Canonical ID Policy Migration Note

## Scope Policy

Canonical ID generation in `wordlift_sdk.kg_build.id_generator.CanonicalIdGenerator`
is policy-driven and supports both graph styles:

- page-centric roots: configured by `IdPolicy.page_root_types` (default: `WebPage`)
- entity-centric roots: configured by `IdPolicy.entity_root_types` (default:
  `Product`, `Service`, `Brand`, with `FinancialProduct` normalized to `Product`)

Nodes are no longer considered page roots only because they have `schema:url`.
Page scope requires explicit page typing/policy membership.

## Deterministic Type Precedence

Multi-typed roots are resolved deterministically using
`IdPolicy.root_type_precedence`. The first matching type in precedence order
selects the canonical container.

Default precedence:

1. `WebPage`
2. `Product`
3. `Service`
4. `Brand`
5. `Offer`
6. `Thing`

## URL Preservation Guarantees

- `schema:url` values are preserved as canonical external URLs.
- IRI rewrites do not rewrite object values of `schema:url`.
- URL-hash suffixing still uses normalized URLs (sorted query parameters) for
  deterministic IDs.

## Media Rewrite Safety

Media rewrites are constrained:

- `schema:image` rewrites only typed `ImageObject` nodes (or already-local
  dependent nodes).
- `schema:video` rewrites only typed `VideoObject` nodes (or already-local
  dependent nodes).
- Arbitrary external IRIs referenced by `schema:image`/`schema:video` are not
  rewritten into internal dataset IRIs.

## Offer/PriceSpecification Completeness

Entity-root canonicalization rewrites all linked `schema:offers` nodes and all
`schema:priceSpecification` nodes per offer, preserving graph linkage across
rewrites.

## Subject IRI Coverage (Callback Graphs)

For `kg_build` callback-emitted graphs, canonicalization now applies a fallback
rewrite pass so every non-blank-node subject IRI is canonicalized into
dataset-rooted paths when needed.

- Existing root/dependent canonicalization rules still run first.
- Subjects already under canonical dataset root prefixes are preserved.
- Non-canonical dataset prefixes (for example `/smallpdf/articles/...`) are
  rewritten to canonical dataset container paths.
- `schema:Action` dependent subjects linked from parents via
  `schema:potentialAction`/`schema:action` are nested under the canonical parent
  IRI path (`<parent>/actions/<slug>`).
- Static template graphs are patched through a separate startup path and are not
  part of callback graph emission rewriting.

## Optional Lookup Reuse

Canonical generation can optionally reuse existing root IRIs through a lookup
hook:

- context key: `Context.extensions["kg_build.iri_lookup"]`
- protocol: `IriLookup.iri_for_subject(graph, subject) -> str | None`
- builtin dataframe implementation:
  `wordlift_sdk.kg_build.DataFrameUrlIriLookup` (`url`/`iri` columns)
- `kg_build` callback contexts populate this lookup from the callback URL and
  `existing_web_page_id` when the URL source already resolved a URL-mapped IRI.

Behavior:

- lookup is applied only to root candidates (first-level URI subjects)
- dependent nodes are not lookup-remapped and still follow canonical
  parent-nested rewrite rules
- duplicate URL rows in dataframe lookup resolve to the shortest IRI path depth
  (tie-break: shorter full IRI, then first row order)
- lookup misses fall back to normal canonical ID generation

## Language-aware ASCII Identifiers

The canonical generator and `IdAllocator` share ASCII slug normalization.
Cloud callbacks and both postprocessor worker modes derive language from
`context.account.language`; direct callers can pass the optional `language`
argument. Language tags are case-insensitive and accept regional forms such
as `de-DE` or `de_DE`. Missing language uses Latin accent transliteration only.

- German applies `ä → ae`, `ö → oe`, `ü → ue`, `ß → ss` (including capitals).
  Other languages retain the generic Latin behavior, such as `ü → u`.
- Russian, Ukrainian, Greek, Arabic, Hebrew, Korean Hangul, and Hindi use
  explicit ICU romanization routes. Mandarin Chinese uses `Han-Latin`.
- Japanese transliterates hiragana and katakana. Kanji, Cantonese, unknown
  scripts, and scripts outside the selected language route do not receive a
  guessed pronunciation. Unsupported characters are omitted from the readable
  slug; an empty result uses `thing`.
- Inputs are normalized to NFC, so canonically equivalent composed and
  decomposed text generates the same identifier. Existing punctuation,
  separators, ASCII-only behavior, and parent nesting conventions remain.

For non-ASCII names without a URL, the readable slug is suffixed with the full
SHA-256 digest of the NFC-normalized, stripped, lowercase original name
(before transliteration), even when romanization succeeds. This prevents distinct
names with the same romanization from merging
across separate callback graphs. Unsupported names use `thing-<digest>`.
Names with a URL keep the existing URL-hash suffix. Identical names without
another identity signal retain their existing ambiguity.
Source-hash identities do not acquire positional sibling suffixes; graph-local
collision suffixes still keep repeated identical names separate. This prevents
sorting newly generated IRIs from changing distinct sibling IDs on a later pass.

Existing authoritative root IRI lookups take precedence over generation.
The fallback pass preserves already canonical dataset IRIs, but explicitly
handled roots and dependents can be regenerated. Changing account language or
regenerating an older non-ASCII identifier can create a new entity, including
when the URL hash is unchanged. This change does not migrate or delete existing
entities automatically: retain lookup mappings when existing root identity
must be preserved.

Transliteration uses PyICU 2.16.2 and native ICU 74.2; installation details are
in [Packaging Slices](packaging_slices_v7.md#native-icu-for-kg-build).

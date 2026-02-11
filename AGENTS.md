# AGENTS

## Project Notes

- Generated Google SHACLs scope contained type requirements under container types
  (for example `ItemList`/`BreadcrumbList` → `ListItem`, `QAPage`/`FAQPage`/`Quiz`
  → `Question`/`Answer`/`Comment`, `ProfilePage` → `Person`/`Organization`,
  `Product` → `Offer`/`AggregateOffer`/`Review`/`AggregateRating`, `Recipe` → `HowToStep`,
  `Course` → `Organization`/`CreativeWork`, `Review` → `Rating`/`AggregateRating`/
  `ItemList`) when both appear in a feature definition. This prevents constraints
  from firing on unrelated nodes.
- The SHACL generator detects "one of" requirements in Google Search Gallery docs
  and emits `sh:or` constraints so any listed property satisfies the requirement.
- Python support is validated against 3.10–3.14; ensure tests pass on 3.14 before
  bumping the range.
- Schema.org grammar checks are deliberately permissive, accepting URL/text literals
  for all properties.
- URL validation can render pages with Playwright, extract JSON-LD fragments, and
  validate them via SHACL. Playwright browser binaries must be installed.
- SSL verification is always enabled; on macOS the SDK uses the system CA bundle
  when available and falls back to `certifi`. Explicit CA bundle overrides are
  supported in the SDK layer.
- Structured data materialization is mapping-preserving by default: no synthetic
  remapping to `ex:*`, no implicit `Review`/`Thing` coercion, and no review-specific
  postprocessing hooks in the generic pipeline.
- Runtime mapping tokens are supported in materialization input:
  `__XHTML__` (local XHTML source path) and `__URL__` (resolved from
  `response.web_page.url` first, then explicit `url` argument; non-strict mode warns
  and keeps unresolved tokens).
- Structured data materialization executes YARRRML directly with `morph-kgc`
  native support; legacy `yarrrml-parser` transpilation is not used.
- Materialization errors are categorized with actionable context for malformed
  YARRRML and unsupported XPath/function constructs.

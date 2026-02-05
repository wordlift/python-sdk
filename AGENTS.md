# AGENTS

## Project Notes

- Generated Google SHACLs scope contained type requirements under container types
  (for example `ItemList`/`BreadcrumbList` → `ListItem`, `QAPage`/`FAQPage`/`Quiz`
  → `Question`/`Answer`/`Comment`, `ProfilePage` → `Person`/`Organization`,
  `Product` → `Offer`, `Recipe` → `HowToStep`, `Course` → `Organization`/`CreativeWork`,
  `Review` → `Rating`/`AggregateRating`) when both appear in a feature definition.
  This prevents constraints from firing on unrelated nodes.
- Python support is validated against 3.10–3.14; ensure tests pass on 3.14 before
  bumping the range.
- Schema.org grammar checks are deliberately permissive, accepting URL/text literals
  for all properties.
- URL validation can render pages with Playwright, extract JSON-LD fragments, and
  validate them via SHACL. Playwright browser binaries must be installed.
- SSL verification is always enabled; on macOS the SDK uses the system CA bundle
  when available and falls back to `certifi`. Explicit CA bundle overrides are
  supported in the SDK layer.

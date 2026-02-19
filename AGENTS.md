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
  `__XHTML__` (local XHTML source path), `__URL__` (resolved from
  `response.web_page.url` first, then explicit `url` argument; non-strict mode warns
  and keeps unresolved tokens), and `__ID__` (resolved from `response.id`;
  unresolved usage fails closed).
- Structured data materialization executes YARRRML directly with `morph-kgc`
  native support; legacy `yarrrml-parser` transpilation is not used.
- `HtmlConverter` sanitizes undeclared namespace prefixes before XHTML
  materialization (`prefix:tag` -> `tag`, undeclared prefixed attributes
  removed) to avoid XML parser `unbound prefix` failures with XPath sources;
  it also removes XML-invalid comments/PIs, validates output with
  `ElementTree.fromstring()`, and applies strict fallback sanitation on parse
  failures.
- Materialization errors are categorized with actionable context for malformed
  YARRRML and unsupported XPath/function constructs.
- `wordlift_sdk.kg_build` is integrated in the SDK with manifest-based
  postprocessor orchestration only; legacy `.py`/`*.command.toml` discovery
  is intentionally removed.
- `wordlift_sdk.kg_build` URL handling uses `WebPageScrapeApi` and conditionally
  runs Search Console refresh when `GOOGLE_SEARCH_CONSOLE` is enabled, while
  the legacy `ApplicationContainer` workflow continues to use web page imports.
- `wordlift_sdk.kg_build` postprocessor subprocesses do not inject package paths
  into `PYTHONPATH`; configured interpreters must resolve their own dependencies.
- `wordlift_sdk.kg_build` postprocessor runtime is configurable via
  `POSTPROCESSOR_RUNTIME`: `oneshot` (default, per-callback runner) or
  `persistent` (one long-lived worker per class across callbacks).
- Retry handlers reference `pydantic_core.ValidationError` via the public API
  (not `pydantic_core._pydantic_core.ValidationError`) for Python 3.14
  compatibility.

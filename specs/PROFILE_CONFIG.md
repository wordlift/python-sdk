# Profile Config Spec

## Purpose

Define a profile-first runtime configuration model for cloud mapping execution.

This model is project-agnostic and does not encode country-specific assumptions.

## Principles

1. Profiles are the primary unit of configuration.
2. `_base` provides inherited defaults.
3. Secrets are injected via environment interpolation (`${ENV_VAR}`).
4. Mapping selection can be URL-routed.
5. Routing is optional; a default mapping is implicitly applied.
6. Postprocessors are loaded from a drop-in folder per profile.
7. Runtime keys are lowercase in TOML and may fallback to uppercase environment variables.

## Config Shape (TOML)

```toml
[profiles._base]
api_key = "${WORDLIFT_API_KEY_DEFAULT}"
strict_mapping = true
mapping = "default.yarrrml"
mapping_mode = "xpath"
api_url = "${API_URL}"
concurrency = "${CONCURRENCY}"
overwrite = "${OVERWRITE}"
urls = "${URLS}"
sitemap_url = "${SITEMAP_URL}"
sitemap_url_pattern = "${SITEMAP_URL_PATTERN}"
sheets_url = "${SHEETS_URL}"
sheets_name = "${SHEETS_NAME}"
sheets_service_account = "${SHEETS_SERVICE_ACCOUNT}"
web_page_import_write_strategy = "${WEB_PAGE_IMPORT_WRITE_STRATEGY}"
web_page_types = "${WEB_PAGE_TYPES}"
embedding_properties = "${EMBEDDING_PROPERTIES}"
web_page_import_mode = "${WEB_PAGE_IMPORT_MODE}"
web_page_import_render_js = "${WEB_PAGE_IMPORT_RENDER_JS}"
web_page_import_wait_for = "${WEB_PAGE_IMPORT_WAIT_FOR}"
web_page_import_country_code = "${WEB_PAGE_IMPORT_COUNTRY_CODE}"
web_page_import_premium_proxy = "${WEB_PAGE_IMPORT_PREMIUM_PROXY}"
web_page_import_block_ads = "${WEB_PAGE_IMPORT_BLOCK_ADS}"
web_page_import_timeout = "${WEB_PAGE_IMPORT_TIMEOUT}"
google_search_console = "${GOOGLE_SEARCH_CONSOLE}"
service_account_file = "${SERVICE_ACCOUNT_FILE}"

[profiles.insurance_faq_v1]
inherit = "_base"
api_key = "${WORDLIFT_API_KEY_INSURANCE_FAQ}"
templates_dir = "profiles/insurance_faq_v1/templates"   # optional
mappings_dir = "profiles/insurance_faq_v1/mappings"      # optional
postprocessors_dir = "profiles/insurance_faq_v1/postprocessors" # optional

[[profiles.insurance_faq_v1.mappings]]
pattern = "^/products/.*$"
mapping = "product.yarrrml"

[[profiles.insurance_faq_v1.mappings]]
pattern = "^/videos/.*$"
mapping = "video.yarrrml"
```

## Defaults

If omitted:

- `inherit`: defaults to `_base` (except profile `_base` itself).
- `templates_dir`: defaults to `profiles/<profile_name>/templates`.
- `mappings_dir`: defaults to `profiles/<profile_name>/mappings`.
- `postprocessors_dir`: defaults to `profiles/<profile_name>/postprocessors`.
- `mapping`: defaults to `default.yarrrml`.
- `mapping_mode`: defaults to `xpath` and currently only `xpath` is valid.

Runtime key fallback:

- For lowercase runtime key `x`, fallback env var is `X` (uppercase), if supported by loader.
- `api_url` special default: `API_URL` env var or `"https://api.wordlift.io"`.
- `urls` default source is env `URLS` when not explicitly set.

Env-fallback runtime keys currently supported:

- `api_url`
- `sitemap_url`
- `sitemap_url_pattern`
- `sheets_url`
- `sheets_name`
- `sheets_service_account`
- `urls`
- `overwrite`
- `concurrency`
- `web_page_import_write_strategy`
- `web_page_types`
- `embedding_properties`
- `web_page_import_mode`
- `web_page_import_render_js`
- `web_page_import_wait_for`
- `web_page_import_country_code`
- `web_page_import_premium_proxy`
- `web_page_import_block_ads`
- `web_page_import_timeout`
- `google_search_console`
- `service_account_file`

## Mapping Routing

`profiles.<name>.mappings` is an ordered list; first regex match wins.

Default behavior:

- If `profiles.<name>.mappings` is missing, runtime behaves as:
  - `pattern = ".*"`, `mapping = "default.yarrrml"`
- If present but no catch-all route exists, runtime appends:
  - `pattern = ".*"`, `mapping = "default.yarrrml"`

Mapping paths are resolved relative to `mappings_dir` unless absolute.

## Inheritance

Resolution model:

1. Resolve parent chain recursively.
2. Merge parent -> child (child overrides).
3. Detect and fail on inheritance cycles with explicit chain in error.

## Environment Interpolation

Supported value format:

- `${ENV_VAR_NAME}`

Resolution rules:

1. Apply interpolation after inheritance merge.
2. If `strict_mapping = true`, missing env values must fail fast.

## Postprocessors

`postprocessors_dir` is a drop-in folder loaded at runtime.

Expected behavior:

1. Load base postprocessors from `profiles/_base/postprocessors.toml` first.
2. Load profile postprocessors from `profiles/<profile>/postprocessors.toml` second.
3. Apply resolved processors to RDFLib graph after mapping materialization.
5. Graph postprocessing is part of runtime flow; no config toggle is required to disable it.
6. Manifest contract:
   - top-level optional defaults: `python`, `timeout_seconds`, `enabled`, `keep_temp_on_error`
   - entries are `[[postprocessors]]` tables
   - required entry field: `class = "package.module:ClassName"`
   - optional per-entry overrides: `python`, `timeout_seconds`, `enabled`, `keep_temp_on_error`
7. Runtime execution contract:
   - each entry runs in subprocess using configured interpreter (`python`)
   - input graph/output graph are exchanged via N-Quads temp files
   - context is exchanged via JSON temp file
   - workflow fails fast on first postprocessor failure

Current shared/base chain:

- project-defined classes loaded from manifest `[[postprocessors]]` entries.
- no customer-specific classes are bundled by the SDK.

Example manifest:

```toml
python = "./.venv/bin/python"
timeout_seconds = 120

[[postprocessors]]
class = "my_project.postprocessors.pricing:PricingPostprocessor"
```

Canonical ID generation is a built-in core step and is not configured as a drop-in postprocessor.

Postprocessor `context` includes:

- `profile_name`
- `url`
- `account`
- `exports`
- `response`
- `settings` (resolved profile runtime settings from config/env)
- `ids` (canonical ID allocator helper)

### Rules Tab Schema (`Pricing Rules`)

`20_pricing.py` and `40_classification.py` are driven by rules loaded from the spreadsheet tab named `Pricing Rules` (or `pricing_rules_sheet` if explicitly provided in runtime settings).

Column contract (case-insensitive, spaces/hyphens normalized to underscores):

- `Country` (optional but recommended): ISO-2 country code (`DE`, `AT`, `CH`, `US`).
- `Pattern` (required): substring matched against page URL path/URL.
- `Category` (optional): used by classification enrichment.
- `Min Price` or `Min` (optional): numeric lower bound for offer pricing.
- `Max Price` or `Max` (optional): numeric upper bound for offer pricing.
- `Currency` (optional): ISO currency code (`EUR`, `CHF`, `USD`).
- `Priority` (optional): integer; higher value wins first.
- `Active` (optional): truthy (`true`, `yes`, `1`, `on`, `active`) or falsy.

Resolution rules:

1. Filter by `Country` matching current profile/account country (if provided).
2. Filter out inactive rows when `Active` is present and falsy.
3. Sort by `Priority` descending.
4. First matching `Pattern` (`pattern in url`) is applied.

## RDF Templates

Profile templates live in `templates_dir` and are rendered/parsed as RDF using any RDFLib-supported format.

Current convention:

- one template file per static entity
- deterministic lexical ordering with numeric prefixes (for example `1_organization.ttl.j2`, `2_website.rdf.j2`)
- Jinja templates (`*.j2`), Liquid templates (`*.liquid`), and static RDF files are supported
- RDF format is inferred from file extension (or extension before `.j2` / `.liquid`) and parsed with RDFLib
- runtime context includes `account` and `dataset_uri` (from `/me`), so templates should use `{{ dataset_uri }}` for dataset-bound IRIs

Sidecar exports:

- profiles define exports in `profiles/<name>/exports.toml`, `profiles/<name>/exports.toml.j2`, or `profiles/<name>/exports.toml.liquid`
- final exports are injected into mapping template context as `exports`
- exports are also available in entity template context (`templates_dir`) to keep shared identifiers in one source
- mapping templates can reference values like `{{ exports.organization_iri }}`

## Non-Goals

This spec does not define:

- converter-specific rule file wiring in `config.toml`
- country-specific profile semantics
- static list-based postprocessor orchestration

## Implementation Notes

Reference implementation lives in:

- `wordlift_sdk/kg_build/config/loader.py`

Public import path:

- `wordlift_sdk.kg_build.config`

Current implementation keeps XHTML placeholder fixed as `__XHTML__` and does not expose customization.

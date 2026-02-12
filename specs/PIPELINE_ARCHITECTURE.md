# Pipeline Architecture Spec

## Purpose

Define the current technical architecture of the SDK `kg_build` profile pipeline.

## Runtime Flow

Cloud workflow is implemented in the SDK under `wordlift_sdk.kg_build`.

## Cloud Workflow

Entry point: host application code that invokes `wordlift_sdk.kg_build.cloud_flow.run_cloud_workflow`.

Core modules:

- `wordlift_sdk/kg_build/cloud_flow.py`
- `wordlift_sdk/kg_build/container.py`
- `wordlift_sdk/kg_build/protocol.py`
- `wordlift_sdk/kg_build/postprocessors.py`

Sequence:

1. Load profile from `config.toml` (`[profiles.<name>]` + inheritance).
2. Resolve runtime settings (env interpolation + fallbacks).
3. Build SDK temp configuration and run `KgImportWorkflow`.
4. For each callback:
   - patch static entity templates once from `profiles/<name>/templates/*`
   - resolve URL-routed mapping from `profiles/<name>/mappings/*`
   - render mapping template with shared `exports`
   - materialize XHTML/XPath mapping
   - reconcile root IRI
   - run postprocessors declared in `profiles/_base/postprocessors.toml` + `profiles/<name>/postprocessors.toml`
   - patch generated graph to WordLift

Debug output convention:

- when cloud debug is enabled, callback graphs are written as Turtle under:
  - `output/debug_cloud/<profile_name>/`
- merged validation for a profile can be run via:
  - `python scripts/validate_debug_cloud.py --profile <name>`
  - uses `wordlift_sdk.validation.validate_file` on a merged Turtle graph

## Cloud Callback Protocol

File: `wordlift_sdk/kg_build/protocol.py`

Responsibility:

1. Receive callback HTML + root ID.
2. Load/patch static template graph once per workflow.
3. Apply profile mapping template for current URL.
4. Reconcile callback root IRI.
5. Apply built-in canonical ID generation (standard policy).
6. Apply profile postprocessors (no hardcoded customer extractor references).
7. Patch graph triples, and optionally write debug Turtle files.

Example profile convention for postprocessors (manifest classes):

- `my_project.postprocessors.webpage:WebPageCorePostprocessor`
- `my_project.postprocessors.products:ProductsPostprocessor`
- `my_project.postprocessors.pricing:PricingPostprocessor`

Loading order:

1. `profiles/_base/postprocessors.toml` (shared defaults)
2. `profiles/<name>/postprocessors.toml` (profile additions/overrides by explicit list)

Entries are executed in list order (base first, then profile).

Runtime-isolated execution:

- each class runs in subprocess using configured interpreter (default `./.venv/bin/python`)
- graph exchange uses temp `nquads` files
- context exchange uses temp JSON
- failures are fail-fast

Current implementation status:

- built-in canonical IDs: implemented in `wordlift_sdk.kg_build.id_generator` + `wordlift_sdk.kg_build.id_policy` + `wordlift_sdk.kg_build.id_postprocessor` (curated dependent policy + independent-by-default behavior)
- manifest-based postprocessor execution (base + profile manifests, subprocess isolation, N-Quads exchange): implemented in `wordlift_sdk.kg_build.postprocessors`.
- profile-specific processors are external to the SDK and loaded by class path from manifests.

## Placeholder Coverage Matrix

This table documents how mapping placeholders are satisfied at runtime in cloud flow.

| Placeholder | Resolution source | Runtime owner | Status |
| --- | --- | --- | --- |
| `$(url)` | Callback URL (mapping input) | Mapping templates (XPath) | Covered |
| `$(name)` | XPath mapping expressions (`<title>` / node text) | Mapping templates (XPath) | Covered |
| `$(description)` | XPath mapping expressions (`<meta name="description">` / node text) | Mapping templates (XPath) | Covered |
| `$(language)` | XPath mapping expressions (`<html lang>`) | Mapping templates (XPath) | Covered |
| `$(html)` | Raw callback HTML | `05_seovoc` (`seovoc:html`) | Covered |
| `$(markdownText)` | HTML->Markdown conversion | `05_seovoc` | Covered |
| `$(image)` | XPath mapping expressions (OpenGraph image) | Mapping templates (XPath) | Covered |
| `$(page_key)` | `sha256(url)[:12]` | built-in canonical ID stage, helpers | Covered |
| `$(product_id)` | Canonical ID generated from Product node + URL hash policy | built-in canonical ID stage | Covered |
| `$(category)` | Existing value or URL-based classification | `40_classification` | Covered |
| `$(offer_price_currency)` | Pricing config + URL match | `20_pricing` | Covered |
| `$(offer_min_price)` | Pricing config + URL match | `20_pricing` | Covered |
| `$(offer_max_price)` | Pricing config + URL match | `20_pricing` | Covered |
| `$(offer_availability)` | Runtime default to `schema:InStock` | `20_pricing` | Covered |
| `$(q_index)` | XPath `count(preceding::...) + 1` expressions | Mapping templates (XPath) | Covered |
| `$(question)` | XPath node extraction from accordion question nodes | Mapping templates (XPath) | Covered |
| `$(answer)` | XPath node extraction from accordion answer nodes | Mapping templates (XPath) | Covered |
| `$(position)` | XPath `count(preceding::...) + 1` expressions | Mapping templates (XPath) | Covered |
| `$(page_type)` (US) | URL-based page classification | `40_classification` | Covered |

Notes:

- `$(` expression placeholders (for example `$(normalize-space(...))`, `$(count(...))`, `$(concat(...))`) are mapping-engine expressions and are not owned by postprocessors.
- Coverage means runtime value is guaranteed by callback HTML + postprocessing chain for currently supported page patterns; new site patterns may require selector updates.

## Cloud Mapping Runtime Status

Implemented:

- `RmlMappingService` is XHTML-first and mapping-only:
  - input: callback HTML (or provided XHTML)
  - materialization backend: `wordlift_sdk.structured_data.materialization.MaterializationPipeline`
  - no extractor-driven JSON materialization inside `apply_mapping`
- Root-ID reconciliation is handled in protocol postprocessing, not inside mapping service.
- Orchestration is owned by `wordlift_sdk.kg_build`.

Pending migration work:

- validate XPath selector robustness across country/site variants and document fallback policy
- static profile entities are loaded from per-entity Jinja Turtle templates (`profiles/<name>/templates/*.ttl.j2`) using account-aware runtime reification (`dataset_uri` from `/me`)
- finalize extractor role as enrichment/postprocessing contract only
- validate schema URI normalization and `@context` handling against parity requirements

## Configuration Model

Primary files:

- `legacy.toml` for legacy local flow
- `config.toml` for profile-driven cloud flow

- Static country extraction/pricing defaults in TOML.
- Remote URL/pricing overrides from Google Sheets.
- Dynamic WordLift dataset/domain from account metadata fetched using country API key.
- Profile-first cloud mapping configuration is defined in `specs/PROFILE_CONFIG.md`:
  - inheritance via `_base`
  - `${ENV_VAR}` interpolation for keys/secrets
  - optional URL-based mapping routing with implicit fallback to `default.yarrrml`
  - drop-in postprocessors loaded from profile folder

## Current Non-Functional Constraints

- Local strategy RML step depends on Docker and `yarrrml-parser`.
- Cloud flow depends on valid profile key and Sheets service account settings (inline JSON or JSON file path).
- Local and cloud parity is a tracked requirement; scripts exist but automated parity tests are not yet part of CI.

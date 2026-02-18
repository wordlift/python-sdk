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

1. Load profile from `worai.toml` (`[profiles.<name>]` + inheritance).
2. Resolve runtime settings (env interpolation + fallbacks).
3. Build SDK temp configuration and run `KgImportWorkflow`.
   - URL handlers run as:
     - `WebPageScrapeUrlHandler` always (`kg_build` path)
     - optional `SearchConsoleUrlHandler` when `GOOGLE_SEARCH_CONSOLE=true`
4. For each callback:
   - patch static entity templates once from `profiles/<name>/templates/*`
   - resolve URL-routed mapping from `profiles/<name>/mappings/*`
   - render mapping template with shared `exports`
   - materialize XHTML/XPath mapping
   - optionally reconcile root IRI when URL source provides an existing ID
   - set `seovoc:source` to `"web-page-import"` in host-generated graph output
   - run postprocessors declared in `profiles/_base/postprocessors.toml` + `profiles/<name>/postprocessors.toml`
   - patch generated graph to WordLift

Debug output convention:

- when cloud debug is enabled, callback graphs are written as Turtle under:
  - `output/debug_cloud/<profile_name>/`
- merged validation can be run by host-project tooling using
  `wordlift_sdk.validation.validate_file`.

## Cloud Callback Protocol

File: `wordlift_sdk/kg_build/protocol.py`

Responsibility:

1. Receive callback HTML plus optional `existing_web_page_id` from URL source.
2. Load/patch static template graph once per workflow.
3. Apply profile mapping template for current URL.
4. Reconcile callback root IRI.
   - only when `existing_web_page_id` is provided
5. Set `seovoc:source` to `"web-page-import"` in the host-side graph before patching.
6. Apply built-in canonical ID generation (standard policy).
7. Apply profile postprocessors (no hardcoded customer extractor references).
8. Patch graph triples, and optionally write debug Turtle files.

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
- runtime mode is selected by `POSTPROCESSOR_RUNTIME` (`oneshot` default, `persistent` optional)
- `oneshot`: launch runner per callback
- `persistent`: launch one worker process per class and reuse it across callbacks
- postprocessor contract:
  - method: `process_graph(self, graph, context)`
  - return: `Graph`, `None`, or awaitable resolving to `Graph | None`
- persistent workers handle one in-flight job at a time per worker instance
- graph exchange uses temp `nquads` files
- context exchange uses temp JSON
- failures are fail-fast

Current implementation status:

- built-in canonical IDs: implemented in `wordlift_sdk.kg_build.id_generator` + `wordlift_sdk.kg_build.id_policy` + `wordlift_sdk.kg_build.id_postprocessor` (curated dependent policy + independent-by-default behavior)
- manifest-based postprocessor execution (base + profile manifests, subprocess isolation, N-Quads exchange): implemented in `wordlift_sdk.kg_build.postprocessors`.
- profile-specific processors are external to the SDK and loaded by class path from manifests.

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

Primary file:

- `worai.toml` for profile-driven cloud flow

- Runtime settings are resolved from profile TOML plus environment interpolation/fallbacks.
- Account metadata (for example `dataset_uri`) is resolved from SDK context at runtime.
- Profile-first cloud mapping configuration is defined in `specs/PROFILE_CONFIG.md`:
  - inheritance via `_base`
  - `${ENV_VAR}` interpolation for keys/secrets
  - optional URL-based mapping routing with implicit fallback to `default.yarrrml`
  - manifest-based postprocessors loaded from
    `profiles/_base/postprocessors.toml` and
    `profiles/<profile>/postprocessors.toml`

## Current Non-Functional Constraints

- Cloud flow depends on valid profile key and Sheets service account settings (inline JSON or JSON file path).
- Automated parity tests are not yet part of CI.

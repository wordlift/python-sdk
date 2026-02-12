# Changelog

## 3.3.0 - 2026-02-12

### Breaking

- Integrated `wordlift_sdk.kg_build` as the SDK-owned profile pipeline and removed candidate naming/API aliases from the public module surface.
- Enforced hard cutover to manifest-based postprocessor orchestration only; legacy `.py` and `*.command.toml` discovery is not supported.

### Added

- Included `wordlift_sdk.kg_build` package modules for profile config loading, cloud workflow orchestration, callback protocol, ID policy/allocation, YARRRML validation, and postprocessor subprocess execution.
- Added SDK docs/specs for profile runtime contracts:
  - `docs/CUSTOMER_PROJECT_CONTRACT.md`
  - `specs/PROFILE_CONFIG.md`
  - `specs/PIPELINE_ARCHITECTURE.md`
- Added dedicated postprocessor contract tests for:
  - base + profile manifest merge ordering
  - subprocess execution
  - N-Quads input/output exchange
  - fail-fast behavior
  - `enabled`, `python`, `timeout_seconds`, `keep_temp_on_error`
- Added direct dependency `jinja2` for Jinja-based KG template rendering.

## 3.2.0 - 2026-02-11

### Breaking

- Refactored structured data materialization to a generic, mapping-preserving pipeline.
- Removed legacy `yarrrml-parser` transpilation from execution path; YARRRML now runs directly through `morph-kgc` native support.
- Removed specialized review-centric behavior from core pipeline execution, including implicit `Review`/`Thing` coercions and review-specific postprocessing hooks.
- Removed `target_type` from `MaterializationPipeline.normalize(...)`, `MaterializationPipeline.postprocess(...)`, and `MaterializationPipeline.run(...)`.
- Removed deprecated `target_type` handling from generic `postprocess_jsonld(...)`.

### Added

- Runtime token replacement before direct materialization execution:
  - `__XHTML__` -> local XHTML source path
  - `__URL__` -> canonical URL resolved from `response.web_page.url` then explicit `url`
  - `__ID__` -> entity IRI resolved from `response.id`
- Strict URL token mode (`strict_url_token=True`) to fail on unresolved `__URL__` tokens.
- Fail-closed ID token handling when `__ID__` is present and unresolved.
- Explicit mapping error categories for malformed YARRRML and unsupported XPath/function constructs.

### Rationale

The SDK core now behaves as a reusable materialization engine for customer-authored mappings, without project-specific semantic assumptions.

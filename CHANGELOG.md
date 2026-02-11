# Changelog

## 3.1.0 - 2026-02-11

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
- Strict URL token mode (`strict_url_token=True`) to fail on unresolved `__URL__` tokens.
- Explicit mapping error categories for malformed YARRRML and unsupported XPath/function constructs.

### Rationale

The SDK core now behaves as a reusable materialization engine for customer-authored mappings, without project-specific semantic assumptions.

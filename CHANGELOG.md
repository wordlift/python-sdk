# Changelog

## 3.0.0 - 2026-02-11

### Breaking

- Refactored structured data materialization to a generic, mapping-preserving pipeline.
- Removed specialized review-centric behavior from core pipeline execution, including implicit `Review`/`Thing` coercions and review-specific postprocessing hooks.
- Removed `target_type` from `MaterializationPipeline.normalize(...)`, `MaterializationPipeline.postprocess(...)`, and `MaterializationPipeline.run(...)`.

### Added

- Runtime token replacement before materialization parser execution:
  - `__XHTML__` -> local XHTML source path
  - `__URL__` -> canonical URL resolved from `response.web_page.url` then explicit `url`
- Strict URL token mode (`strict_url_token=True`) to fail on unresolved `__URL__` tokens.

### Rationale

The SDK core now behaves as a reusable materialization engine for customer-authored mappings, without project-specific semantic assumptions.

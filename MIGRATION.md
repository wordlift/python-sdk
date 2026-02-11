# Migration Guide

## 3.0.0 Breaking Changes

The structured data materialization pipeline was refactored to be generic and mapping-preserving.

## What Was Removed

- Synthetic remapping of authored mappings into internal `ex:*` structures.
- Implicit coercion/defaulting toward `Review`/`Thing` in the generic materialization path.
- Review-specific postprocessing side effects in core pipeline execution:
  - `_dedupe_review_notes`
  - `_ensure_review_url`
  - review author/rating injection/pruning hooks

## Signature Changes

`MaterializationPipeline` now removes `target_type` from generic materialization flow methods:

- `normalize(self, yarrrml: str, url: str, xhtml_path: Path) -> tuple[str, list[dict]]`
- `postprocess(self, jsonld_raw: dict, mappings: list[dict], cleaned_xhtml: str, dataset_uri: str, url: str) -> dict`
- `run(self, yarrrml: str, url: str, cleaned_xhtml: str, dataset_uri: str, xhtml_path: Path, workdir: Path, response: object | None = None, strict_url_token: bool = False) -> tuple[dict, list[dict]]`

## Runtime Tokens

Mappings can use runtime tokens before materialization:

- `__XHTML__`: replaced with local XHTML source path.
- `__URL__`: resolved from `response.web_page.url` first, then explicit `url` argument.

URL token resolution policy:
- strict mode (`strict_url_token=True`): fail if unresolved
- default mode: warn and keep `__URL__` unchanged

## How To Migrate Legacy Specialized Consumers

If your integration relied on previous review-specific behavior, move that behavior to an adapter outside SDK core:

1. Materialize using the SDK generic pipeline.
2. Apply your review-specific transformations in your own postprocessing layer.
3. Validate transformed output against the shapes you require.

This keeps the SDK customer-agnostic while preserving custom behavior in your project.

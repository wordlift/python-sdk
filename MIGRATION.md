# Migration Guide

## 3.1.0 Breaking Changes

The structured data materialization pipeline was refactored to be generic and mapping-preserving.

## What Was Removed

- Synthetic remapping of authored mappings into internal `ex:*` structures.
- Implicit coercion/defaulting toward `Review`/`Thing` in the generic materialization path.
- Legacy JS transpile path (`yarrrml-parser` -> temporary RML `.ttl`) in the materialization pipeline.
- Review-specific postprocessing side effects in core pipeline execution:
  - `_dedupe_review_notes`
  - `_ensure_review_url`
  - review author/rating injection/pruning hooks

## Signature Changes

`MaterializationPipeline` now removes `target_type` from generic materialization flow methods:

- `normalize(self, yarrrml: str, url: str, xhtml_path: Path, response: object | None = None) -> tuple[str, list[dict]]`
- `postprocess(self, jsonld_raw: dict, mappings: list[dict], cleaned_xhtml: str, dataset_uri: str, url: str) -> dict`
- `run(self, yarrrml: str, url: str, cleaned_xhtml: str, dataset_uri: str, xhtml_path: Path, workdir: Path, response: object | None = None, strict_url_token: bool = False) -> tuple[dict, list[dict]]`

`postprocess_jsonld(...)` in the generic YARRRML pipeline also no longer accepts `target_type`.

## Runtime Tokens

Mappings can use runtime tokens before materialization:

- `__XHTML__`: replaced with local XHTML source path.
- `__URL__`: resolved from `response.web_page.url` first, then explicit `url` argument.
- `__ID__`: resolved from `response.id`.

URL token resolution policy:
- strict mode (`strict_url_token=True`): fail if unresolved
- default mode: warn and keep `__URL__` unchanged

ID token resolution policy:
- fail-closed if `__ID__` appears and no runtime ID is available

## Materialization Engine Migration

The SDK now passes YARRRML directly to `morph-kgc`.

What to update from legacy transpile flow:
1. Remove operational dependencies on `yarrrml-parser` in your runtime.
2. Validate mappings against `morph-kgc` native YARRRML behavior.
3. Update XPath/function expressions that relied on parser-specific transpile behavior.

## How To Migrate Legacy Specialized Consumers

If your integration relied on previous review-specific behavior, move that behavior to an adapter outside SDK core:

1. Materialize using the SDK generic pipeline.
2. Apply your review-specific transformations in your own postprocessing layer.
3. Validate transformed output against the shapes you require.

This keeps the SDK customer-agnostic while preserving custom behavior in your project.

## 5.0.0 Ingestion Model Update

The SDK now provides a formal 2-axis ingestion model:

- Source axis (`INGEST_SOURCE`): `auto|urls|sitemap|sheets|local`
- Loader axis (`INGEST_LOADER`): `auto|simple|proxy|playwright|premium_scraper|web_scrape_api|passthrough`

### Defaults

- Global default loader is now `web_scrape_api`.
- If `INGEST_LOADER` and `WEB_PAGE_IMPORT_MODE` are both unset, loader resolves to `web_scrape_api`.

### Compatibility Mapping

| Legacy `WEB_PAGE_IMPORT_MODE` | New behavior |
| --- | --- |
| `default` | `web_scrape_api` |
| `proxy` | `proxy` |
| `premium_scraper` | `premium_scraper` |

### Precedence

1. `INGEST_*` keys win over legacy keys.
2. If `INGEST_*` is unset, SDK resolves using legacy keys.
3. If both are set and disagree, SDK uses `INGEST_*` and emits machine-parseable warning `INGEST_CFG_CONFLICT`.

### Passthrough Policy

If an item includes embedded HTML and `INGEST_PASSTHROUGH_WHEN_HTML=true`, SDK
uses `passthrough` before network loaders.

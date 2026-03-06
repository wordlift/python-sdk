# Local Agent Type Classification Spec

## Purpose

Provide a reusable SDK method that combines ingestion with local CLI-based
schema type suggestion export.

## Public API

- `wordlift_sdk.ingestion.create_type_classification_csv_from_ingestion(...)`

Inputs:

- `source_bundle`: mapping containing ingestion config (`INGEST_SOURCE`,
  `INGEST_LOADER`, source-specific keys, optional `URL_REGEX`)
- `output_csv`: output path
- `agent_cli`: optional explicit CLI (`claude|codex|gemini`)
- `agent_timeout_sec`
- `max_markdown_chars`
- `on_progress`: optional callback receiving progress payloads

Output columns:

- `url`
- `main_type`
- `additional_types` (JSON array string)
- `explanation`

## Behavioral Contract

- Uses shared `run_ingestion` for page loading.
- Applies global ingestion URL filtering (`URL_REGEX`) before loader execution.
- Markdown extraction uses `trafilatura` only.
- CLI selection:
  - explicit `agent_cli` if provided
  - otherwise auto-detect first installed CLI in this exact order:
    `claude`, `codex`, `gemini`
- Prompt requests strict JSON with keys:
  `main_type`, `additional_types`, `explanation`.
- Fails when extraction or CLI execution/JSON parsing fails.
- `on_progress(payload)` callback events:
  - `type_classification.progress.started` with `meta.total`
  - `type_classification.progress.updated` with
    `meta.total`, `meta.completed`, `meta.remaining`, `meta.url`, `meta.status`
  - Failure updates include `meta.error_type`, `meta.error_message` before
    the exception is re-raised.
  - `type_classification.progress.completed` with
    `meta.total`, `meta.completed` (success-only terminal event).

## Backward Compatibility

- `SITEMAP_URL_PATTERN` is deprecated in ingestion config.
- For `INGEST_SOURCE=sitemap`, when `URL_REGEX` is unset, resolver maps
  `SITEMAP_URL_PATTERN` to `url_regex` and emits a deprecation warning.

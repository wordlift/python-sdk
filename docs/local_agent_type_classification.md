# Local Agent Type Classification

Use `wordlift_sdk.ingestion.create_type_classification_csv_from_ingestion` to:

1. ingest pages via the shared `INGEST_SOURCE` + `INGEST_LOADER` pipeline
2. extract meaningful markdown body with `trafilatura`
3. classify each URL via a local non-interactive agent CLI
4. write `url,main_type,additional_types,explanation` CSV output

## API

```python
from wordlift_sdk.ingestion import create_type_classification_csv_from_ingestion

df = create_type_classification_csv_from_ingestion(
    source_bundle={
        "INGEST_SOURCE": "urls",
        "INGEST_LOADER": "web_scrape_api",
        "URLS": ["https://example.com/a", "https://example.com/b"],
        "URL_REGEX": r"^https://example.com/",
        "WORDLIFT_KEY": "your-api-key",
    },
    output_csv="url-types.csv",
    agent_cli=None,  # auto-pick: claude -> codex -> gemini
    concurrency="auto",  # adaptive worker count by default
    no_resume=False,  # default: resume from local sidecar state when available
)
```

Progress callbacks are optional and intended for host/UI rendering:

```python
events: list[dict[str, object]] = []

create_type_classification_csv_from_ingestion(
    source_bundle={...},
    output_csv="url-types.csv",
    on_progress=events.append,
)
```

## Notes

- `URL_REGEX` is global and source-agnostic.
- `SITEMAP_URL_PATTERN` remains accepted for sitemap only, but is deprecated.
- `agent_cli=None` auto-selects the first installed CLI in order:
  `claude`, then `codex`, then `gemini`.
- Classification uses adaptive concurrency by default (`concurrency="auto"`)
  via the shared `AutoConcurrencyController`. Fixed worker counts are also
  supported by passing an integer string such as `"4"`.
- Runs are resumable by default via a local sidecar state file next to the CSV.
  The resume key is based on the call state, excluding the selected CLI, so a
  resumed run can continue even if `agent_cli` changes between executions.
  Concurrency settings are intentionally excluded from the resume-state
  identity.
- Pass `no_resume=True` to ignore any existing local resume state and reprocess
  all pages from scratch.
- `additional_types` is serialized as JSON array text in the CSV cell.
- Per-page classification retries up to 2 additional times with a 3-second wait
  between attempts. If classification still fails, the run continues and the CSV
  row is written with empty `main_type`, `additional_types=[]`, and an error note
  in `explanation`.
- `on_progress(payload)` emits:
  - `type_classification.progress.started` (`meta.total`)
  - `type_classification.progress.updated`
    (`meta.total`, `meta.completed`, `meta.remaining`, `meta.url`, `meta.status`)
    and on skipped failures also `meta.error_type`, `meta.error_message`.
  - `type_classification.progress.completed` (`meta.total`, `meta.completed`)

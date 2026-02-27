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
)
```

## Notes

- `URL_REGEX` is global and source-agnostic.
- `SITEMAP_URL_PATTERN` remains accepted for sitemap only, but is deprecated.
- `agent_cli=None` auto-selects the first installed CLI in order:
  `claude`, then `codex`, then `gemini`.
- `additional_types` is serialized as JSON array text in the CSV cell.

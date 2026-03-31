# Semantic Area Profiler PoC

## Technical Design

`wordlift_sdk.ingestion.semantic_area_profiler` is split into explicit stages:

1. Sitemap URL discovery
2. URL filtering (`website_url` boundary, then optional `url_regex`)
3. Deterministic sampling
4. Page inspection (ingestion orchestrator + selected loader)
5. Semantic inference (main entity + additional recurring entities)
6. Semantic normalization (dataset-scoped deterministic IDs)
7. Output serialization (flat JSON-LD graph)

## Input Schema

`SemanticAreaProfileRequest`:

- `sitemap: str` (required)
- `website_url: str` (required)
- `url_regex: str | None` (optional)
- `sample_size: int` (default `12`)
- `sampling_strategy: str` (`round_robin_bucket` or `hash_stride`, default `round_robin_bucket`)
- `sampling_seed: str | int | None` (optional)
- `inspect_loader: str` (default `simple`)
- `inspect_timeout_ms: int` (default `30000`)
- `inspect_retry_attempts: int` (default `1`)
- `inspect_retry_backoff_ms: int` (default `0`)
- `main_entity_min_confidence: float` (default `0.6`)
- `strict_mode: bool` (default `False`)
- `dataset_uri: str | None` (optional)
- `api_key: str | None` (optional; used for runtime dataset resolution)
- `base_url: str` (default `https://api.wordlift.io`)
- `ssl_ca_cert: str | None` (optional)

## Output Schema

`SemanticAreaProfileResult`:

- `scope: dict`
- `main_entity: str`
- `additional_entity_types: list[str]`
- `explanation: str`
- `explanation_metadata: dict`
- `sampled_web_pages: list[{url, canonical, title}]`
- `sample_semantic_data: {"@context": "https://schema.org", "@graph": [ ... ]}`

## Sampling Strategies

- `round_robin_bucket`: URLs are grouped by first relative path segment under `website_url`; one URL per bucket is selected in round-robin order.
- `hash_stride`: URLs are sorted by SHA-256 hash of `<seed>|<normalized_url>` for deterministic pseudo-randomized selection.

## Coherence Heuristic

- `coherent`: dominant type share high enough and clearly ahead
- `mixed`: dominant and runner-up both materially present
- `ambiguous`: insufficient dominance or weak evidence

## Strict Mode

When `strict_mode=True`, post-serialization validation enforces:

- dataset-scoped IDs
- no fragment IDs
- no duplicate IDs
- no inline anonymous nested objects
- dependent-node nesting under parent IDs when parent predicate links are present
- rejection of non-schema-like property keys (e.g. keys containing `:`)
- rejection of non-dataset IRI references for non-URL properties

## Example

```json
{
  "scope": {
    "sitemap": "https://example.com/sitemap.xml",
    "website_url": "https://example.com/articles",
    "matched_url_count": 24,
    "sample_size": 12,
    "sampled_url_count": 12,
    "sampling_strategy": "round_robin_bucket",
    "sampling_seed": null,
    "inspect_loader": "simple"
  },
  "main_entity": "Article",
  "additional_entity_types": ["Organization", "BreadcrumbList"],
  "explanation": "main_entity_reason=page votes were {'Article': 10}. main_confidence=0.8333. ...",
  "explanation_metadata": {
    "coherence": "coherent",
    "main_confidence": 0.8333,
    "vote_counts": {"Article": 10}
  },
  "sampled_web_pages": [
    {
      "url": "https://example.com/articles/a",
      "canonical": "https://example.com/articles/a",
      "title": "Article A"
    }
  ],
  "sample_semantic_data": {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@id": "https://dataset.example/articles/article-a-<sha256>",
        "@type": "http://schema.org/Article",
        "url": "https://example.com/articles/a"
      }
    ]
  }
}
```

## Assumptions

- If `dataset_uri` is omitted, runtime resolution is attempted via `StructuredDataEngine.get_dataset_uri` and `api_key`.
- Inspection uses existing ingestion loaders (`simple`, `playwright`, `web_scrape_api`, etc.) through `IngestionOrchestrator`.

## Limitations

- Inference is heuristic and tuned for PoC behavior; not a full semantic classifier.
- Strict mode is intentionally conservative and may reject noisy real-world payloads.
- No automatic multi-cluster discovery.

## Next Steps

1. Add configurable per-type evidence weights from an external profile file.
2. Add richer schema-aware strict validation against selected SHACL profiles.
3. Add benchmark fixtures from real customer domains for calibration.

# KG Build KPI And Validation Callbacks

This guide defines the client contract for `kg_build` sync telemetry:
- in-run progress events via `on_progress`
- final run summary via `on_kpi`

## Entry Point

Use `wordlift_sdk.kg_build.cloud_flow.run_cloud_workflow`:

- `on_progress(dict) | None`: called during sync for each graph processed.
- `on_kpi(dict) | None`: called once at run end with cumulative KPIs.
- `on_info(str) | None`: legacy informational stream; fully supported and can be
  used together with `on_progress` and `on_kpi`.

## Validation Settings

Validation is optional and controlled by profile settings:

- `shacl_validate_sync` / `SHACL_VALIDATE_SYNC`: `true|false` (default `false`)
- `shacl_validate_mode` / `SHACL_VALIDATE_MODE`: `warn|strict` (default `warn`)
- `shacl_shape_specs` / `SHACL_SHAPE_SPECS`: optional shape names/files (list or comma-separated string)

Behavior:

- `warn`: validation results are included in payloads; sync continues on failures.
- `strict`: failing graph/static-template events are emitted first with
  `validation.pass = false`, then sync raises and stops that graph path.

## In-Run Progress Payload (`on_progress`)

### Graph event

```json
{
  "kind": "graph",
  "profile": "avalara",
  "url": "https://example.com/page-1",
  "graph": {
    "entities": 14,
    "type_assertions": 21,
    "property_assertions": 132
  },
  "validation": {
    "total": 1,
    "pass": true,
    "fail": false,
    "warnings": {
      "count": 2,
      "sources": {
        "google-article": 2
      }
    },
    "errors": {
      "count": 0,
      "sources": {}
    }
  }
}
```

### Static template event

```json
{
  "kind": "static_templates",
  "profile": "avalara",
  "graph": {
    "entities": 8,
    "type_assertions": 8,
    "property_assertions": 34
  },
  "validation": null
}
```

Notes:

- `validation` is `null` when SHACL validation is disabled.
- `graph` counts are dataset-scoped (only entities matching account dataset URI).
- `kind="static_templates"` is emitted once per run during startup bootstrap,
  even when URL callbacks execute concurrently.

## Final KPI Payload (`on_kpi`)

```json
{
  "run_id": "2026-02-24T15:12:03Z",
  "profile": "avalara",
  "totals": {
    "total_entities": 1284,
    "type_assertions_total": 1917,
    "property_assertions_total": 12402
  },
  "entities_by_type": {
    "https://schema.org/WebPage": 412,
    "https://schema.org/Article": 388
  },
  "properties_by_predicate": {
    "https://schema.org/name": 1284,
    "https://schema.org/url": 1210,
    "https://w3id.org/seovoc/source": 1284
  },
  "validation": {
    "total": 413,
    "pass": 397,
    "fail": 16,
    "warnings": {
      "count": 42,
      "sources": {
        "google-article": 18,
        "google-product-snippet": 24
      }
    },
    "errors": {
      "count": 89,
      "sources": {
        "google-article": 28,
        "google-product-snippet": 61
      }
    }
  }
}
```

When `validation` is present: `validation.total == validation.pass + validation.fail`.

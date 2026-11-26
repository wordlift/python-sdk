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

- `shacl_validate_mode` / `SHACL_VALIDATE_MODE`: `off|warn|fail` (default `warn`)
- `shacl_builtin_shapes` / `SHACL_BUILTIN_SHAPES`: optional bundled shape allowlist
- `shacl_exclude_builtin_shapes` / `SHACL_EXCLUDE_BUILTIN_SHAPES`: optional bundled shape denylist
- `shacl_extra_shapes` / `SHACL_EXTRA_SHAPES`: optional list/comma-separated local paths or remote URLs

Behavior:

- `off`: validation payloads are `null`; sync continues.
- `warn`: validation results are included in payloads; sync continues on failures.
- `fail`: failing graph/static-template events are emitted first with
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
- payload schema is unchanged by validation-mode/shape-resolution settings; only
  the content of `validation` changes (`null` in `off`, summary object in `warn`/`fail`).

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

## Run Report Files (`output_dir`)

When `CloudWorkflowConfig.output_dir` is set, `run_cloud_workflow` writes:

- `graph_sync_report.md`: run totals and top processing errors. When SHACL
  validation is on (`warn`/`fail`), it adds a **Structured Data Errors**
  section: pages validated, pages with errors, total errors, and the 10 rules
  affecting the most pages, each with an example URL and message.
- `graph_sync_failures.csv`: pages that failed to process (only when there are
  failures).
- `graph_sync_validation.csv`: one row per SHACL error (severity
  `sh:Violation`; warnings are not listed). Written only when validation is on.
  The header is always written, so a file with only a header means every page
  passed.

`graph_sync_validation.csv` columns:

| Column | Content |
| --- | --- |
| `url` | Page URL, or `static_templates` for the static template graph |
| `severity` | Always `error` |
| `rule_set` | Shape set (bundled shape name or extra shape file stem), for example `google-product-snippet` |
| `rule_id` | IRI of the named shape that failed. An anonymous property shape takes the IRI of the named shape holding it. |
| `path` | Property path, dotted for sequence paths (for example `offers.price`) |
| `focus_node` | Node that failed the rule |
| `value` | Offending value, when SHACL reports one |
| `message` | SHACL result message |

Rows are appended as each page is validated, so memory does not grow with the
number of pages; only per-rule totals for the markdown section are kept in
memory. At most 100 errors are listed per page (`MAX_ERROR_DETAILS_PER_GRAPH`);
error counts stay exact and the markdown notes pages with omitted rows.

Protocols opt in by exposing `enable_validation_report(path)`; the bundled
`ProfileImportProtocol` does, and returns `None` when validation is `off`.

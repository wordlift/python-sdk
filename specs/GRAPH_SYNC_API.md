# Graph Sync API

## Purpose

Define a backend API and persistence model for recording graph sync runs with:

- one durable run record per graph sync execution
- live progress while a run is executing
- aggregate KPI snapshots during execution and at completion
- detailed per-URL reporting, including SHACL validation details

This API is intended to wrap the existing `kg_build` telemetry contract instead
of replacing it. Current SDK hooks already emit:

- in-run graph progress via `on_progress`
- final aggregate KPI via `on_kpi`
- run-level KPI generation via `ProfileImportProtocol.get_kpi_summary()`

The backend described here persists those signals, extends them with
run lifecycle and per-URL events, and exposes them via a resource-oriented REST
API.

## Design Principles

The API should follow the Zalando RESTful API guidelines at a high level:

- resource-oriented URLs
- plural collection names
- kebab-case path segments
- snake_case JSON field names
- RFC 3339 timestamps
- standard HTTP semantics and status codes
- `application/problem+json` for error responses
- cursor-based pagination for collections
- OpenAPI-first contract definition

## Resource Model

The graph is the top-level business resource. Sync runs are a sub-resource of a
graph.

Canonical resource hierarchy:

- `/graphs/{graph_id}`
- `/graphs/{graph_id}/sync-runs`
- `/graphs/{graph_id}/sync-runs/{run_id}`
- `/graphs/{graph_id}/sync-runs/{run_id}/urls`
- `/graphs/{graph_id}/sync-runs/{run_id}/urls/{url_id}`
- `/graphs/{graph_id}/sync-runs/{run_id}/events`

Notes:

- `run_id` should be a stable server-generated identifier such as a UUID or ULID.
- `url_id` should not be the raw URL path-encoded into the URL. Prefer a stable
  derived identifier such as a hash of the canonical URL.
- Raw URL values remain available in resource payloads.

## Core Use Cases

1. Create a new sync run for a graph.
2. Observe live run progress while the run is executing.
3. Read aggregate KPI snapshots for the run.
4. Inspect per-URL results for success, failure, skip, and SHACL validation.
5. Audit the raw event stream for debugging and replay.
6. Query the history of sync runs for a graph.

## Backend Architecture

Recommended logical components:

### GraphSyncRunService

Owns run lifecycle transitions:

- create run
- mark running
- mark completed
- mark failed
- mark cancelled

### GraphSyncEventIngestService

Accepts immutable telemetry events from the SDK or host application:

- run lifecycle events
- progress updates
- KPI snapshots
- per-URL result events

### GraphSyncProjectionService

Projects append-only events into queryable read models:

- run summary
- run progress counters
- aggregate KPI snapshot
- per-URL materialized status

### GraphSyncQueryService

Serves the REST API from the projected read models.

## Integration With Existing SDK Runtime

Current `kg_build` behavior already provides the foundation:

- `run_cloud_workflow(..., on_progress=...)` emits per-graph progress payloads
- `run_cloud_workflow(..., on_kpi=...)` emits a final KPI payload
- `ProfileImportProtocol` calculates validation summaries per graph
- `KgBuildKpiCollector` aggregates cumulative totals across the run

The backend plan should add:

1. explicit workflow-level `run_id` injection rather than collector-local ID generation
2. lifecycle events at run start and terminal completion/failure
3. per-URL events emitted from the callback path
4. incremental aggregate KPI snapshots during execution
5. durable persistence and query APIs

Recommended SDK extension point:

- introduce a recorder interface used alongside `on_progress` and `on_kpi`

Example shape:

```python
class GraphSyncRunRecorder(Protocol):
    def record_run_started(self, payload: dict[str, Any]) -> None: ...
    def record_progress(self, payload: dict[str, Any]) -> None: ...
    def record_url_result(self, payload: dict[str, Any]) -> None: ...
    def record_kpi_snapshot(self, payload: dict[str, Any]) -> None: ...
    def record_run_completed(self, payload: dict[str, Any]) -> None: ...
    def record_run_failed(self, payload: dict[str, Any]) -> None: ...
```

## Persistence Model

PostgreSQL with JSONB is the recommended default. It supports:

- append-only event storage
- indexed queryable run summaries
- indexed per-URL reports
- gradual schema evolution without over-engineering

### `graphs`

Top-level graph resource metadata.

Fields:

- `graph_id`
- `name` nullable
- `created_at`
- `updated_at`

### `graph_sync_runs`

One row per sync execution.

Fields:

- `run_id`
- `graph_id`
- `profile_name`
- `status`
- `source_kind`
- `started_at`
- `completed_at` nullable
- `updated_at`
- `triggered_by` nullable
- `workflow_config` JSONB
- `progress` JSONB
- `totals` JSONB
- `validation` JSONB nullable
- `error` JSONB nullable

Recommended `status` values:

- `QUEUED`
- `RUNNING`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

Recommended `progress` shape:

- `urls_total`
- `urls_started`
- `urls_succeeded`
- `urls_failed`
- `urls_skipped`

### `graph_sync_run_urls`

Materialized per-URL run state.

Fields:

- `url_id`
- `run_id`
- `graph_id`
- `url`
- `status`
- `started_at` nullable
- `completed_at` nullable
- `existing_web_page_id` nullable
- `existing_import_hash` nullable
- `graph` JSONB nullable
- `validation` JSONB nullable
- `validation_issues` JSONB nullable
- `error` JSONB nullable
- `diagnostics` JSONB nullable
- `artifacts` JSONB nullable

Recommended `status` values:

- `PENDING`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `SKIPPED`

Unique key:

- `(run_id, url_id)`

### `graph_sync_run_events`

Immutable event store for auditability and replay.

Fields:

- `event_id`
- `graph_id`
- `run_id`
- `sequence_no`
- `event_type`
- `occurred_at`
- `url_id` nullable
- `payload` JSONB

Unique keys:

- `(run_id, sequence_no)`
- optional external idempotency key if events may be retried by the sender

### Optional `graph_sync_run_kpi_snapshots`

Only needed if aggregate KPI history must be queryable independently from the
raw event log.

Fields:

- `run_id`
- `sequence_no`
- `captured_at`
- `totals` JSONB
- `entities_by_type` JSONB
- `properties_by_predicate` JSONB
- `validation` JSONB nullable

## Event Model

The event log is the write model. Run and URL tables are projections.

Recommended event types:

- `run.started`
- `run.progress.updated`
- `run.kpi.updated`
- `run.completed`
- `run.failed`
- `static-templates.synced`
- `url.started`
- `url.graph.built`
- `url.validation.completed`
- `url.synced`
- `url.failed`
- `url.skipped`

Base event envelope:

```json
{
  "schema_version": 1,
  "event_id": "01JXYZ...",
  "graph_id": "graph-123",
  "run_id": "01JXYZ...",
  "event_type": "url.validation.completed",
  "sequence_no": 42,
  "occurred_at": "2026-03-13T10:22:11Z",
  "url_id": "8f4d...",
  "payload": {}
}
```

## Validation Reporting Model

Each per-URL report should persist both a compact summary and a detailed issue list.

### `validation`

Compact per-URL summary aligned with the current SDK shape:

- `total`
- `pass`
- `fail`
- `warnings.count`
- `warnings.sources`
- `errors.count`
- `errors.sources`

### `validation_issues`

Normalized issue records for drilldown UI and operator workflows.

Recommended fields:

- `level`
- `severity`
- `focus_node`
- `result_path`
- `rule_id`
- `rule_set`
- `message`

If payload size becomes large, the issue list may be moved to a separate table
or object storage while keeping the summary inline on the URL resource.

## REST API Contract

### Create Run

`POST /graphs/{graph_id}/sync-runs`

Purpose:

- create a new sync run for a graph

Request body:

```json
{
  "profile_name": "avalara",
  "source_kind": "SITEMAP",
  "triggered_by": "scheduler",
  "workflow_config": {
    "sitemap_url": "https://example.com/sitemap.xml"
  }
}
```

Behavior:

- server creates a new `run_id`
- server returns `201 Created`
- response includes `Location` header to the created resource
- support `Idempotency-Key` header for safe client retries

### List Runs

`GET /graphs/{graph_id}/sync-runs`

Query params:

- `status`
- `profile_name`
- `created_from`
- `created_to`
- `cursor`
- `limit`

Behavior:

- returns a paginated collection of run summaries for the graph

### Get Run

`GET /graphs/{graph_id}/sync-runs/{run_id}`

Behavior:

- returns the current run summary, progress, aggregate KPI, validation summary,
  and hypermedia links to sub-resources

Example response:

```json
{
  "run_id": "01JXYZ...",
  "graph_id": "graph-123",
  "profile_name": "avalara",
  "status": "RUNNING",
  "source_kind": "SITEMAP",
  "started_at": "2026-03-13T10:22:11Z",
  "completed_at": null,
  "progress": {
    "urls_total": 1240,
    "urls_started": 511,
    "urls_succeeded": 488,
    "urls_failed": 23,
    "urls_skipped": 0
  },
  "totals": {
    "total_entities": 1284,
    "type_assertions_total": 1917,
    "property_assertions_total": 12402
  },
  "validation": {
    "total": 489,
    "pass": 470,
    "fail": 19,
    "warnings": {
      "count": 42,
      "sources": {
        "google-article": 18
      }
    },
    "errors": {
      "count": 89,
      "sources": {
        "google-product-snippet": 61
      }
    }
  },
  "_links": {
    "self": {
      "href": "/graphs/graph-123/sync-runs/01JXYZ..."
    },
    "urls": {
      "href": "/graphs/graph-123/sync-runs/01JXYZ.../urls"
    },
    "events": {
      "href": "/graphs/graph-123/sync-runs/01JXYZ.../events"
    }
  }
}
```

### List Per-URL Reports

`GET /graphs/{graph_id}/sync-runs/{run_id}/urls`

Query params:

- `status`
- `validation_pass`
- `has_errors`
- `cursor`
- `limit`

Behavior:

- returns paginated per-URL materialized state for the run

### Get Per-URL Report

`GET /graphs/{graph_id}/sync-runs/{run_id}/urls/{url_id}`

Behavior:

- returns detailed status, graph metrics, validation summary, detailed SHACL
  issues, diagnostics, and artifacts for one URL

Example response:

```json
{
  "url_id": "8f4d...",
  "run_id": "01JXYZ...",
  "graph_id": "graph-123",
  "url": "https://example.com/page-1",
  "status": "FAILED",
  "started_at": "2026-03-13T10:23:01Z",
  "completed_at": "2026-03-13T10:23:08Z",
  "graph": {
    "entities": 14,
    "type_assertions": 21,
    "property_assertions": 132
  },
  "validation": {
    "total": 1,
    "pass": false,
    "fail": true,
    "warnings": {
      "count": 2,
      "sources": {
        "google-article": 2
      }
    },
    "errors": {
      "count": 1,
      "sources": {
        "google-article": 1
      }
    }
  },
  "validation_issues": [
    {
      "level": "error",
      "severity": "http://www.w3.org/ns/shacl#Violation",
      "rule_set": "google-article",
      "rule_id": "headline-required",
      "message": "Missing headline"
    }
  ],
  "error": {
    "code": "SHACL_VALIDATION_FAILED",
    "message": "Graph validation failed"
  }
}
```

### List Events

`GET /graphs/{graph_id}/sync-runs/{run_id}/events`

Query params:

- `cursor`
- `limit`
- `event_type`
- `url_id`

Behavior:

- returns the immutable event stream for debugging and replay

## Live Progress

The canonical source of truth is the run resource plus its event collection.

Recommended live-progress options:

1. polling `GET /graphs/{graph_id}/sync-runs/{run_id}`
2. polling `GET /graphs/{graph_id}/sync-runs/{run_id}/events`
3. optional SSE endpoint outside the core REST surface if low-latency updates are required

If SSE is added, keep the REST resources authoritative and treat SSE as a
delivery optimization only.

## Error Model

Error responses should use `application/problem+json`.

Typical cases:

- `400 Bad Request` for malformed filters or invalid request payloads
- `404 Not Found` when `graph_id`, `run_id`, or `url_id` does not exist
- `409 Conflict` for illegal run state transitions
- `422 Unprocessable Entity` for semantically invalid create-run requests
- `429 Too Many Requests` for throttled API callers
- `500`/`502`/`503` for server-side failures

## Operational Concerns

### Concurrency

Runs process URLs concurrently. The backend must handle:

- concurrent event ingestion for the same run
- deterministic per-run ordering via `sequence_no`
- idempotent retries for duplicated event delivery

### Failure Semantics

Special handling is required for:

- SHACL `fail` mode, where the SDK emits failure context before raising
- workflow failures after partial progress
- per-URL skips for HTTP error pages or out-of-scope URLs

The backend should preserve partial KPI and event history even for failed runs.

### Payload Size

Per-URL validation issues and diagnostics may become large. If needed:

- keep summaries inline
- move large issue arrays or artifacts to separate storage
- expose references from the URL resource

## Suggested Delivery Phases

### Phase 1

- define OpenAPI contract
- implement `graph_sync_runs` and `graph_sync_run_events`
- persist current SDK `on_progress` and `on_kpi` signals
- support run create/list/get and event list APIs

### Phase 2

- add explicit SDK run lifecycle events
- add `graph_sync_run_urls`
- persist per-URL state and errors
- expose URL list/detail APIs

### Phase 3

- persist normalized SHACL issue lists
- add validation filters to URL collection APIs
- add richer diagnostics/artifact references

### Phase 4

- optional SSE stream
- alerting and operational dashboards
- replay tooling from stored events

## Testing Strategy

Recommended test coverage:

- unit tests for SDK event emission ordering
- projection tests from event log to run and URL tables
- API contract tests for pagination, filtering, and problem responses
- failure-path tests for workflow failure and SHACL fail mode
- idempotency tests for duplicate event delivery
- concurrency tests for multiple URL updates within one run

## Recommended Default

The default design should be:

- graph-scoped resource model under `/graphs/{graph_id}/sync-runs`
- append-only event ingestion plus projected read models
- PostgreSQL JSONB persistence
- OpenAPI-first definition
- backward-compatible reuse of existing `kg_build` telemetry hooks

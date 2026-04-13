# Specs Index

Release sync: this index is aligned with SDK `8.0.15` (see `CHANGELOG.md`).

- `specs/GSC_CANONICAL_SELECTION.md`: Client integration spec for canonical URL election from GSC impressions (`url,title` CSV input, OAuth/service-account credential handoff, interval/concurrency contract).
- `specs/GRAPH_SYNC_API.md`: Graph-scoped REST API and persistence model for recording sync runs, live progress, aggregate KPIs, and per-URL SHACL reporting.
- `specs/PIPELINE_ARCHITECTURE.md`: `kg_build` runtime flow and callback architecture.
- `specs/PROFILE_CONFIG.md`: Profile inheritance, environment interpolation, and postprocessor manifest contract.
- `specs/INGESTION_PIPELINE.md`: Source/loader ingestion contract, resolver precedence rules, and `kg_build` bridge callback suppression contract for HTTP error pages.
- `specs/LOCAL_AGENT_TYPE_CLASSIFICATION.md`: Ingestion-backed local CLI classification contract and CSV output schema.
- `specs/structured_data.md`: Structured data runtime placeholder/materialization details.
- `specs/PACKAGING_SLICES_V7.md`: v7 packaging, extras, lazy-import, and slice-verification contract.
- `specs/validation.md`: Validation architecture and shape composition contract.
- `specs/tls.md`: TLS/SSL CA bundle resolution behavior.
- `specs/versioning.md`: Versioning and release process rules.
- `README.md`: high-level install and slice-consumer guide that should stay consistent with the packaging/versioning specs.

# Docs Index

Release sync: this index is aligned with SDK `8.0.17` (see `CHANGELOG.md`).

- `docs/public_entry_points.md`: Task-oriented public API inventory for clients/agents.
- `docs/packaging_slices_v7.md`: v7 packaging model for lean base installs plus optional feature extras under the same `wordlift_sdk` namespace.
- `README.md`: high-level install guide, slice summary, and common verification commands.
- `docs/ingestion_pipeline.md`: Two-axis ingestion architecture, config precedence, compatibility mapping, async-safe Playwright loader behavior, Playwright failure diagnostics in `ingest.item_failed.meta`, bridge-handler diagnostics surfacing (`diagnostics=<json>`), and `kg_build` callback suppression for HTTP error pages (`status_code >= 400`).
- `docs/local_agent_type_classification.md`: Ingestion-backed local CLI (`claude|codex|gemini`) type classification CSV export (`url,main_type,additional_types,explanation`) with `trafilatura` markdown extraction.
- `docs/structured_data.md`: Structured data architecture and workflows.
- `docs/validation.md`: SHACL validation usage, bundled/custom shape selection, and SDK-side issue filtering helpers.
- `docs/search_gallery_shacl_review.md`: Current page-by-page SHACL change review for Search Gallery pages with extracted sample conformance metrics.
- `docs/render.md`: Page rendering and XHTML cleanup options.
- `docs/web_page_import.md`: Web page import handler behavior and fetch options.
- `docs/kg_build_kpi_and_validation.md`: Client contract for `kg_build` in-run progress (`on_progress`) and final KPI (`on_kpi`) payloads, including SHACL validation fields.
- `docs/kg_build_cloud_workflow_migration.md`: Migration guide to canonical `run_cloud_workflow`, source-mode selection, and runtime defaults.
- `docs/worai_sdk_integration_contract_v6.md`: Worai-facing integration contract for SDK v6 (canonical path, explicit source/loader, callbacks, and conformance matrix).
- `docs/google_sheets_lookup.md`: Google Sheets lookup utility.
- `docs/google_search_console_canonical_selection.md`: Canonical URL election from `url,title` CSV using GSC impressions, interval parsing, regex filtering, and fixed/auto adaptive concurrency.
- `docs/html_converter.md`: HTML conversion helper behavior.
- `docs/canonical_id_policy.md`: Canonical ID scope policy, type precedence, and URL/media rewrite guarantees.
- `docs/CUSTOMER_PROJECT_CONTRACT.md`: Profile repository contract for `kg_build`, including `_base`/profile override semantics for postprocessors, runtime settings, and exports manifests.

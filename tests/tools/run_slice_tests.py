from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


SLICE_TESTS: dict[str, list[str]] = {
    "core": [
        "tests/test_client_configuration_factory.py",
        "tests/test_configuration_get_config_value.py",
        "tests/test_lazy_exports.py",
        "tests/utils/test_auto_concurrency.py",
    ],
    "google-sheets": [
        "tests/google_sheets/test_google_sheets_lookup.py",
        "tests/test_utils_create_dataframe_from_google_sheets.py",
    ],
    "render": [
        "tests/test_render_browser.py",
        "tests/test_render_html_renderer.py",
        "tests/test_xhtml_cleaner.py",
    ],
    "validation": [
        "tests/test_validation_helpers.py",
        "tests/test_validation_from_url.py",
        "tests/test_search_gallery_samples_validation.py",
        "tests/test_recommended_one_of_validation.py",
        "tests/test_merchant_listing_defined_region_validation.py",
        "tests/test_product_snippet_validation.py",
        "tests/test_schemaorg_domain_validation.py",
        "tests/test_shacl_generator.py",
        "tests/test_validation_generator_more.py",
    ],
    "google-search-console": [
        "tests/test_google_search_console_canonical_selection.py",
        "tests/test_google_search_console_data_import_helpers.py",
    ],
    "ingestion": [
        "tests/ingestion",
        "tests/test_google_sheets_url_provider.py",
        "tests/test_list_url_provider.py",
        "tests/url_provider/test_sitemap_url_provider.py",
    ],
    "structured-data": [
        "tests/test_dataset_resolver.py",
        "tests/test_structured_data_batch.py",
        "tests/test_structured_data_engine_class.py",
        "tests/test_structured_data_engine_utils.py",
        "tests/test_structured_data_engine_validation_helpers.py",
        "tests/test_structured_data_inputs.py",
        "tests/test_structured_data_io_and_validation.py",
        "tests/test_structured_data_materialization_generic.py",
        "tests/test_structured_data_orchestrator_rendering.py",
        "tests/test_structured_data_workflows.py",
        "tests/test_yarrrml_pipeline.py",
    ],
    "workflow": [
        "tests/test_main.py",
        "tests/test_web_page_import_fetch_options.py",
        "tests/workflow/test_kg_import_workflow.py",
    ],
    "graph": [
        "tests/test_graph_audit.py",
    ],
    "kg-build": [
        "tests/kg_build",
    ],
    "legacy": [
        "tests/test_graphql_query_helpers.py",
        "tests/test_google_search_console_data_import_helpers.py",
        "tests/test_ingestion_source_bridge.py",
        "tests/test_protocol_and_render_helpers.py",
    ],
    "all": [
        "tests",
    ],
}


def _existing_targets(targets: list[str]) -> list[str]:
    return [target for target in targets if Path(target).exists()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the pytest subset that defines a packaging slice."
    )
    parser.add_argument("slice", choices=sorted(SLICE_TESTS))
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print test targets for the selected slice and exit.",
    )
    args, extra_args = parser.parse_known_args()

    targets = _existing_targets(SLICE_TESTS[args.slice])
    if not targets:
        raise SystemExit(f"No test targets configured for slice '{args.slice}'.")

    if args.list:
        for target in targets:
            print(target)
        return 0

    if extra_args[:1] == ["--"]:
        extra_args = extra_args[1:]

    command = [sys.executable, "-m", "pytest", *targets, *extra_args]
    print("Running:", shlex.join(command))
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())

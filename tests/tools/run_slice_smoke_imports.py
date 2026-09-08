from __future__ import annotations

import argparse
import importlib
import tempfile
from pathlib import Path


SLICE_IMPORTS: dict[str, list[str]] = {
    "core": [
        "wordlift_sdk",
        "wordlift_sdk.client",
        "wordlift_sdk.configuration",
    ],
    "google-sheets": [
        "wordlift_sdk.google_sheets",
        "wordlift_sdk.url_source",
    ],
    "render": [
        "wordlift_sdk.render",
    ],
    "validation": [
        "wordlift_sdk.validation",
    ],
    "google-search-console": [
        "wordlift_sdk.google_search_console",
    ],
    "ingestion": [
        "wordlift_sdk.ingestion",
        "wordlift_sdk.url_source",
    ],
    "structured-data": [
        "wordlift_sdk.structured_data",
    ],
    "workflow": [
        "wordlift_sdk",
        "wordlift_sdk.container",
        "wordlift_sdk.protocol",
        "wordlift_sdk.workflow",
    ],
    "graph": [
        "wordlift_sdk.graph",
    ],
    "kg-build": [
        "wordlift_sdk",
        "wordlift_sdk.kg_build",
    ],
    "legacy": [
        "wordlift_sdk.deprecated",
        "wordlift_sdk.entity",
        "wordlift_sdk.internal_link",
        "wordlift_sdk.kg",
        "wordlift_sdk.utils",
    ],
    "all": [
        "wordlift_sdk",
        "wordlift_sdk.container",
        "wordlift_sdk.deprecated",
        "wordlift_sdk.entity",
        "wordlift_sdk.google_search_console",
        "wordlift_sdk.google_sheets",
        "wordlift_sdk.graph",
        "wordlift_sdk.ingestion",
        "wordlift_sdk.internal_link",
        "wordlift_sdk.kg",
        "wordlift_sdk.kg_build",
        "wordlift_sdk.protocol",
        "wordlift_sdk.render",
        "wordlift_sdk.structured_data",
        "wordlift_sdk.url_source",
        "wordlift_sdk.utils",
        "wordlift_sdk.validation",
        "wordlift_sdk.workflow",
    ],
}


SLICE_EXPORTS: dict[str, list[tuple[str, str]]] = {
    "core": [],
    "google-sheets": [("wordlift_sdk.google_sheets", "GoogleSheetsLookup")],
    "render": [
        ("wordlift_sdk.render", "CleanupOptions"),
        ("wordlift_sdk.render", "HtmlRenderer"),
        ("wordlift_sdk.render", "RenderOptions"),
        ("wordlift_sdk.render", "XhtmlCleaner"),
    ],
    "validation": [
        ("wordlift_sdk.validation", "ValidationResult"),
        ("wordlift_sdk.validation", "validate_file"),
    ],
    "google-search-console": [
        (
            "wordlift_sdk.google_search_console",
            "create_canonical_csv_from_gsc_impressions",
        ),
    ],
    "ingestion": [
        ("wordlift_sdk.ingestion", "run_ingestion"),
        ("wordlift_sdk.ingestion", "create_source_registry"),
        ("wordlift_sdk.url_source", "SitemapUrlSource"),
    ],
    "structured-data": [
        ("wordlift_sdk.structured_data", "CreateRequest"),
        ("wordlift_sdk.structured_data", "StructuredDataEngine"),
    ],
    "workflow": [
        ("wordlift_sdk", "run_kg_import_workflow"),
        ("wordlift_sdk.container", "ApplicationContainer"),
        ("wordlift_sdk.protocol", "Context"),
        ("wordlift_sdk.workflow", "KgImportWorkflow"),
    ],
    "graph": [
        ("wordlift_sdk.graph", "GraphAuditor"),
    ],
    "kg-build": [
        ("wordlift_sdk", "kg_build"),
        ("wordlift_sdk.kg_build", "run_cloud_workflow"),
        ("wordlift_sdk.kg_build", "KgBuildApplicationContainer"),
    ],
    "legacy": [
        ("wordlift_sdk.deprecated", "create_entities_with_top_query_dataframe"),
        ("wordlift_sdk.entity", "enrich"),
        ("wordlift_sdk.internal_link", "create_internal_link_handler"),
        ("wordlift_sdk.kg", "EntityStore"),
        ("wordlift_sdk.utils", "create_entity_patch_request"),
    ],
    "all": [
        ("wordlift_sdk", "run_kg_import_workflow"),
        ("wordlift_sdk", "kg_build"),
        ("wordlift_sdk", "ingestion"),
        ("wordlift_sdk.validation", "validate_file"),
        ("wordlift_sdk.structured_data", "CreateRequest"),
        (
            "wordlift_sdk.google_search_console",
            "create_canonical_csv_from_gsc_impressions",
        ),
    ],
}


def _smoke_validation() -> None:
    validation = importlib.import_module("wordlift_sdk.validation")
    shape_names = validation.list_shape_names()
    assert "google-article.ttl" in shape_names
    resolved = validation.resolve_shape_specs(
        builtin_shapes=["google-article"],
        exclude_builtin_shapes=["schemaorg-grammar"],
    )
    assert "google-article.ttl" in resolved
    print("call ok: validation.list_shape_names/resolve_shape_specs")


def _smoke_ingestion() -> None:
    ingestion = importlib.import_module("wordlift_sdk.ingestion")
    config = ingestion.resolve_ingestion_config_from_mapping(
        {
            "INGEST_SOURCE": "urls",
            "INGEST_LOADER": "simple",
            "URLS": ["https://example.com/article"],
            "URL_REGEX": r"^https://example.com/",
        }
    )
    assert config.source_name == "urls"
    assert config.loader_name == "simple"
    assert config.url_regex == r"^https://example.com/"
    source_registry = ingestion.create_source_registry()
    loader_registry = ingestion.create_loader_registry()
    assert source_registry.resolve("urls") is not None
    assert loader_registry.resolve("simple") is not None
    print("call ok: ingestion.resolve_ingestion_config_from_mapping/create_*_registry")


def _smoke_kg_build() -> None:
    kg_build = importlib.import_module("wordlift_sdk.kg_build")
    icu = importlib.import_module("icu")
    assert icu.ICU_VERSION == "74.2"
    slug = importlib.import_module(
        "wordlift_sdk.kg_build.postprocessors.processors.slug"
    )
    assert slug.normalize_slug("Müller", "de") == "mueller"
    assert slug.normalize_slug("Москва", "ru") == "moskva"
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "worai.toml"
        config_path.write_text(
            """
[profiles.alpha]
mapping = "default.yarrrml"
api_url = "https://api.wordlift.io"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        config = kg_build.load_profile_config(config_path)
        profile = config.get("alpha")
        assert (
            profile.resolve_mapping("https://example.com/article") == "default.yarrrml"
        )
    print("call ok: kg_build.load_profile_config/language-aware slugs")


SLICE_CALLS = {
    "validation": _smoke_validation,
    "ingestion": _smoke_ingestion,
    "kg-build": _smoke_kg_build,
    "all": _smoke_kg_build,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import the public modules and exports for a packaging slice."
    )
    parser.add_argument("slice", choices=sorted(SLICE_IMPORTS))
    args = parser.parse_args()

    for module_name in SLICE_IMPORTS[args.slice]:
        importlib.import_module(module_name)
        print(f"import ok: {module_name}")

    for module_name, attr_name in SLICE_EXPORTS[args.slice]:
        module = importlib.import_module(module_name)
        getattr(module, attr_name)
        print(f"export ok: {module_name}.{attr_name}")

    smoke = SLICE_CALLS.get(args.slice)
    if smoke is not None:
        smoke()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

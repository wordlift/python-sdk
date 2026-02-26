from __future__ import annotations

import json
from pathlib import Path

from wordlift_sdk.validation.shacl import validate_file


FIXTURES_ROOT = Path("tests/fixtures/search_gallery")
MANIFEST_PATH = FIXTURES_ROOT / "manifest.json"
SHAPES_ROOT = Path("wordlift_sdk/validation/shacls")


def _load_manifest() -> dict[str, dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _has_context(payload: dict | list) -> bool:
    if isinstance(payload, dict):
        return "@context" in payload
    if isinstance(payload, list):
        return any(isinstance(item, dict) and "@context" in item for item in payload)
    return False


def test_search_gallery_sample_fixtures_exist_for_broadly_changed_pages() -> None:
    manifest = _load_manifest()
    expected_core = {
        "article",
        "book",
        "education-qa",
        "image-license-metadata",
        "job-posting",
        "local-business",
        "return-policy",
        "shipping-policy",
    }
    assert len(manifest) >= 30
    assert expected_core.issubset(set(manifest.keys()))

    for slug in expected_core:
        entry = manifest[slug]
        assert entry["raw_samples"], f"Missing raw samples for {slug}"

    # Most Search Gallery feature pages expose code snippets.
    nonempty_raw_pages = sum(1 for entry in manifest.values() if entry["raw_samples"])
    assert nonempty_raw_pages >= 35


def test_search_gallery_jsonld_samples_validate_against_page_shapes() -> None:
    manifest = _load_manifest()
    conforming_by_slug: dict[str, int] = {}

    for slug, entry in manifest.items():
        shape_name = f"google-{slug}"
        shape_path = SHAPES_ROOT / f"{shape_name}.ttl"
        if not shape_path.exists():
            continue
        conforming_by_slug.setdefault(slug, 0)
        for sample in entry["jsonld_samples"]:
            sample_path = Path(sample["path"])
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
            result = validate_file(sample_path.as_posix(), shape_specs=[shape_name])
            if _has_context(payload):
                if result.conforms:
                    conforming_by_slug[slug] += 1

    # Core pages touched by recent SHACL fixes must keep at least one conforming
    # full-context Search Gallery sample.
    assert conforming_by_slug["article"] >= 1
    assert conforming_by_slug["education-qa"] >= 1
    assert conforming_by_slug["image-license-metadata"] >= 1
    assert conforming_by_slug["local-business"] >= 1

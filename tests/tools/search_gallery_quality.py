from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from wordlift_sdk.validation.shacl import validate_file

FIXTURES_ROOT = Path("tests/fixtures/search_gallery")
MANIFEST_PATH = FIXTURES_ROOT / "manifest.json"
SHAPES_ROOT = Path("wordlift_sdk/validation/shacls")


def _has_context(payload: dict | list) -> bool:
    if isinstance(payload, dict):
        return "@context" in payload
    if isinstance(payload, list):
        return any(isinstance(item, dict) and "@context" in item for item in payload)
    return False


@dataclass
class SampleOutcome:
    slug: str
    sample_id: str
    path: str
    conforms: bool


def _load_manifest() -> dict[str, dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def compute_outcomes() -> list[SampleOutcome]:
    manifest = _load_manifest()
    outcomes: list[SampleOutcome] = []

    for slug, entry in manifest.items():
        shape_name = f"google-{slug}"
        shape_path = SHAPES_ROOT / f"{shape_name}.ttl"
        if not shape_path.exists():
            continue
        for sample in entry["jsonld_samples"]:
            sample_path = Path(sample["path"])
            payload = json.loads(sample_path.read_text(encoding="utf-8"))
            if not _has_context(payload):
                continue
            result = validate_file(sample_path.as_posix(), shape_specs=[shape_name])
            outcomes.append(
                SampleOutcome(
                    slug=slug,
                    sample_id=sample.get("id", sample_path.stem),
                    path=sample_path.as_posix(),
                    conforms=result.conforms,
                )
            )

    return outcomes


def summarize_outcomes(outcomes: list[SampleOutcome]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for outcome in outcomes:
        bucket = summary.setdefault(
            outcome.slug,
            {
                "total_with_context": 0,
                "conforming": 0,
                "failing_sample_ids": [],
            },
        )
        bucket["total_with_context"] += 1
        if outcome.conforms:
            bucket["conforming"] += 1
        else:
            bucket["failing_sample_ids"].append(outcome.sample_id)
    return summary


def main() -> int:
    summary = summarize_outcomes(compute_outcomes())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

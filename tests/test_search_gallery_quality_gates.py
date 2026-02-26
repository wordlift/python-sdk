from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.tools.search_gallery_quality import compute_outcomes, summarize_outcomes


BASELINE_PATH = Path("tests/fixtures/search_gallery/baseline_conformance.json")
EXPECTATIONS_PATH = Path("tests/fixtures/search_gallery/expectations.json")


@pytest.fixture(scope="module")
def current_summary() -> dict[str, dict]:
    return summarize_outcomes(compute_outcomes())


def test_search_gallery_conformance_does_not_regress_against_baseline(
    current_summary: dict[str, dict],
) -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    for slug, expected in baseline.items():
        assert slug in current_summary, (
            f"Missing current conformance summary for slug: {slug}"
        )
        assert (
            current_summary[slug]["total_with_context"]
            >= expected["total_with_context"]
        ), (
            f"Context sample count dropped for {slug}: "
            f"{current_summary[slug]['total_with_context']} < {expected['total_with_context']}"
        )
        assert current_summary[slug]["conforming"] >= expected["conforming"], (
            f"Conformance regressed for {slug}: "
            f"{current_summary[slug]['conforming']} < {expected['conforming']}"
        )


def test_search_gallery_known_nonconforming_samples_are_explicit(
    current_summary: dict[str, dict],
) -> None:
    expectations = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))

    for slug, bucket in current_summary.items():
        actual_failing = set(bucket["failing_sample_ids"])
        expected_failing = set(
            expectations.get(slug, {}).get("known_nonconforming_sample_ids", [])
        )

        unexpected = sorted(actual_failing - expected_failing)
        stale = sorted(expected_failing - actual_failing)

        assert not unexpected, (
            f"Unexpected failing samples for {slug}: {unexpected}. "
            "Update parser/shapes or expectations.json."
        )
        assert not stale, (
            f"Stale expected failures for {slug}: {stale}. "
            "Remove outdated entries from expectations.json."
        )

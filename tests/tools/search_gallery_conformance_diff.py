from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.tools.search_gallery_quality import (  # noqa: E402
    compute_outcomes,
    summarize_outcomes,
)


BASELINE_PATH = Path("tests/fixtures/search_gallery/baseline_conformance.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Search Gallery conformance against committed baseline."
    )
    parser.add_argument(
        "--allow-regression",
        action="store_true",
        help="Print regressions without failing.",
    )
    args = parser.parse_args(argv)

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    current = summarize_outcomes(compute_outcomes())

    regressed: list[str] = []

    print("| Page | Baseline | Current | Delta |")
    print("|---|---:|---:|---:|")
    for slug in sorted(baseline):
        b = baseline[slug]
        c = current.get(slug, {"conforming": 0, "total_with_context": 0})
        b_ratio = f"{b['conforming']}/{b['total_with_context']}"
        c_ratio = f"{c['conforming']}/{c['total_with_context']}"
        delta = c["conforming"] - b["conforming"]
        print(f"| {slug} | {b_ratio} | {c_ratio} | {delta:+d} |")
        if delta < 0 or c["total_with_context"] < b["total_with_context"]:
            regressed.append(slug)

    if regressed:
        print("")
        print(f"Regressed pages: {', '.join(regressed)}")
        return 0 if args.allow_regression else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

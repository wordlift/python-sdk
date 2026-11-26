"""Per-run report of the SHACL errors found in synced pages.

Rows are appended to a CSV as each page is validated, so memory does not grow
with the number of pages or errors. Only per-rule totals are kept in memory,
for the markdown summary added to ``graph_sync_report.md``.
"""

from __future__ import annotations

import csv
import threading
from dataclasses import dataclass, field
from pathlib import Path

from wordlift_sdk.kg_build.report_util import _md_cell
from wordlift_sdk.validation.shacl_validation_service import (
    MAX_ERROR_DETAILS_PER_GRAPH,
    ValidationOutcome,
)

VALIDATION_CSV_NAME = "graph_sync_validation.csv"
STATIC_TEMPLATES_LABEL = "static_templates"
CSV_HEADER = (
    "url",
    "severity",
    "rule_set",
    "rule_id",
    "path",
    "focus_node",
    "value",
    "message",
)
_TOP_RULES = 10

# (rule_set, rule_id, path): anonymous property shapes resolve to their parent
# shape's id, so the path is what tells two of its properties apart.
_RuleKey = tuple[str, str | None, str | None]


@dataclass
class _RuleStats:
    pages: int = 0
    errors: int = 0
    example_url: str = ""
    example_message: str = ""


@dataclass
class _RunStats:
    pages_validated: int = 0
    pages_with_errors: int = 0
    errors: int = 0
    pages_with_omitted_errors: int = 0
    rules: dict[_RuleKey, _RuleStats] = field(default_factory=dict)


class ValidationReportWriter:
    """Streams one CSV row per SHACL error and keeps per-rule totals."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._stats = _RunStats()
        path.parent.mkdir(parents=True, exist_ok=True)
        # The header is written up front, so an empty file means the pages were
        # validated and none had errors.
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(CSV_HEADER)

    @property
    def path(self) -> Path:
        return self._path

    def record(self, url: str, outcome: ValidationOutcome) -> None:
        with self._lock:
            stats = self._stats
            stats.pages_validated += 1
            if outcome.error_count == 0:
                return
            stats.pages_with_errors += 1
            stats.errors += outcome.error_count
            if outcome.error_count > len(outcome.errors):
                stats.pages_with_omitted_errors += 1

            seen_on_page: set[_RuleKey] = set()
            with self._path.open("a", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                for error in outcome.errors:
                    writer.writerow(
                        (
                            url,
                            "error",
                            error.rule_set,
                            error.rule_id or "",
                            error.path or "",
                            error.focus_node or "",
                            error.value or "",
                            error.message,
                        )
                    )
                    key = (error.rule_set, error.rule_id, error.path)
                    rule = stats.rules.get(key)
                    if rule is None:
                        rule = stats.rules[key] = _RuleStats(
                            example_url=url, example_message=error.message
                        )
                    rule.errors += 1
                    if key not in seen_on_page:
                        seen_on_page.add(key)
                        rule.pages += 1

    def render_markdown(self) -> str:
        with self._lock:
            stats = self._stats
            lines = [
                "## Structured Data Errors",
                "",
                "| Metric | Value |",
                "| --- | --- |",
                f"| Pages validated | **{stats.pages_validated}** |",
                f"| Pages with errors | **{stats.pages_with_errors}** |",
                f"| Errors | **{stats.errors}** |",
            ]
            if not stats.rules:
                return "\n".join(lines) + "\n"
            ranked = sorted(
                stats.rules.items(),
                key=lambda item: (
                    -item[1].pages,
                    -item[1].errors,
                    item[0][0],
                    item[0][1] or "",
                    item[0][2] or "",
                ),
            )
            lines += [
                "",
                "### Top errors by pages affected",
                "",
                "| Pages | Errors | Shape set | Rule | Path | Example URL | Message |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for (rule_set, rule_id, path), rule in ranked[:_TOP_RULES]:
                lines.append(
                    f"| {rule.pages}"
                    f" | {rule.errors}"
                    f" | `{_md_cell(rule_set)}`"
                    f" | `{_md_cell(_short_rule(rule_id))}`"
                    f" | `{_md_cell(path or '-')}`"
                    f" | {_md_link(rule.example_url)}"
                    f" | {_md_cell(rule.example_message)} |"
                )
            remaining = len(ranked) - _TOP_RULES
            if remaining > 0:
                lines.append(f"\n_…and {remaining} more rule(s)._")
            lines.append(f"\nThe errors are listed one per row in `{self._path.name}`.")
            if stats.pages_with_omitted_errors:
                lines.append(
                    f"{stats.pages_with_omitted_errors} page(s) had more than "
                    f"{MAX_ERROR_DETAILS_PER_GRAPH} errors; only the first "
                    f"{MAX_ERROR_DETAILS_PER_GRAPH} of each are listed."
                )
            return "\n".join(lines) + "\n"


def _short_rule(rule_id: str | None) -> str:
    """Last path segment of a rule IRI, which is unique within its shape set."""
    if not rule_id:
        return "-"
    return rule_id.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1] or rule_id


def _md_link(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return f"[{_md_cell(url)}]({url.replace('|', '%7C').replace(' ', '%20')})"
    return f"`{_md_cell(url)}`"


__all__ = [
    "CSV_HEADER",
    "STATIC_TEMPLATES_LABEL",
    "VALIDATION_CSV_NAME",
    "ValidationReportWriter",
]

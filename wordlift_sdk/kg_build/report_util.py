from __future__ import annotations

import csv
import io
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wordlift_sdk.workflow.kg_import_workflow import KgImportResult
    from wordlift_sdk.workflow.url_handler.default_url_handler import FailedUrl

_URL_RE = re.compile(r"https?://\S*")
_TOP_ERRORS = 10
_ERROR_PREFIX_LEN = 80


def _md_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    h, remainder = divmod(s, 3600)
    m, sec = divmod(remainder, 60)
    if h:
        return f"{h}h {m}m {sec}s"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


def _format_success_rate(url_count: int, success_count: int) -> str:
    if url_count == 0:
        return "N/A"
    return f"{success_count / url_count * 100:.1f}%"


def _error_key(message: str) -> str:
    """Return a stable grouping key by stripping URL-specific segments."""
    stripped = _URL_RE.sub("", message).strip(": ")
    key = stripped or message
    return key[:_ERROR_PREFIX_LEN]


def render_as_markdown(result: KgImportResult) -> str:
    success_count = max(result.url_count - len(result.failures), 0)
    lines = [
        "# Graph Sync Report",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total URLs | **{result.url_count}** |",
        f"| Successes | **{success_count}** |",
        f"| Failures | **{len(result.failures)}** |",
        f"| Success rate | **{_format_success_rate(result.url_count, success_count)}** |",
        f"| Execution time | **{_format_duration(result.elapsed_seconds)}** |",
    ]
    if result.failures:
        examples: dict[str, object] = {}
        for f in result.failures:
            key = _error_key(f.message)
            if key not in examples:
                examples[key] = f
        counts = Counter(_error_key(f.message) for f in result.failures)
        lines += [
            "",
            "## Top Errors",
            "",
            "| Count | Error | Example URL | Full error |",
            "| --- | --- | --- | --- |",
        ]
        for key, count in counts.most_common(_TOP_ERRORS):
            ex = examples[key]
            lines.append(
                f"| {count}"
                f" | `{_md_cell(key)}`"
                f" | [{_md_cell(ex.url.value)}]({ex.url.value.replace('|', '%7C')})"
                f" | `{_md_cell(ex.message)}` |"
            )
        remaining = len(counts) - _TOP_ERRORS
        if remaining > 0:
            lines.append(
                f"\n_…and {remaining} more error type(s). See the CSV for the full list._"
            )
    return "\n".join(lines) + "\n"


def render_as_csv(failures: list[FailedUrl]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "url", "error"])
    for f in failures:
        writer.writerow([f.timestamp.isoformat(), f.url.value, f.message])
    return buf.getvalue()


def write_report(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

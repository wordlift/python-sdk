from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wordlift_sdk.workflow.kg_import_workflow import KgImportResult
    from wordlift_sdk.workflow.url_handler.default_url_handler import FailedUrl


def _format_timestamp(dt: datetime) -> str:
    return dt.strftime(f"%b {dt.day}, %H:%M:%S UTC")


def _md_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")


def render_as_markdown(result: KgImportResult) -> str:
    success_count = max(result.url_count - len(result.failures), 0)
    lines = [
        "# Graph Sync Report",
        "",
        f"Total URLs: **{result.url_count}**",
        f"Successes: **{success_count}**",
        f"Failures: **{len(result.failures)}**",
        "",
        "## Failures",
        "",
        "| Timestamp (UTC) | URL | Handler | Error |",
        "| --- | --- | --- | --- |",
    ]
    for f in result.failures:
        lines.append(
            f"| {_format_timestamp(f.timestamp)}"
            f" | `{_md_cell(f.url.value)}`"
            f" | `{_md_cell(f.handler_name)}`"
            f" | `{_md_cell(f.message)}` |"
        )
    return "\n".join(lines) + "\n"


def render_as_csv(failures: list[FailedUrl]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "url", "handler", "error"])
    for f in failures:
        writer.writerow(
            [f.timestamp.isoformat(), f.url.value, f.handler_name, f.message]
        )
    return buf.getvalue()


def write_report(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

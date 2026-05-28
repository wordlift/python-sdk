from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from types import SimpleNamespace


from wordlift_sdk.kg_build.report_util import (
    _format_timestamp,
    _md_cell,
    render_as_csv,
    render_as_markdown,
    write_report,
)


def _failure(url="https://example.com", handler="Handler", message="boom", ts=None):
    return SimpleNamespace(
        timestamp=ts or datetime(2026, 4, 2, 14, 5, 9, tzinfo=timezone.utc),
        url=SimpleNamespace(value=url),
        handler_name=handler,
        message=message,
    )


def _result(url_count=1, failures=None):
    return SimpleNamespace(
        url_count=url_count, failures=failures if failures is not None else []
    )


# --- _md_cell ---


def test_md_cell_escapes_pipe():
    assert _md_cell("hello|world") == "hello\\|world"


def test_md_cell_escapes_newline():
    assert _md_cell("line1\nline2") == "line1 line2"


def test_md_cell_escapes_both():
    assert _md_cell("a|b\nc") == "a\\|b c"


def test_md_cell_plain_text_unchanged():
    assert _md_cell("no special chars") == "no special chars"


# --- _format_timestamp ---


def test_format_timestamp_no_zero_padding_on_day():
    dt = datetime(2026, 4, 2, 14, 5, 9, tzinfo=timezone.utc)
    assert _format_timestamp(dt) == "Apr 2, 14:05:09 UTC"


def test_format_timestamp_midnight_hours_not_corrupted():
    dt = datetime(2026, 4, 1, 0, 5, 9, tzinfo=timezone.utc)
    assert _format_timestamp(dt) == "Apr 1, 00:05:09 UTC"


def test_format_timestamp_double_digit_day():
    dt = datetime(2026, 4, 15, 14, 5, 9, tzinfo=timezone.utc)
    assert _format_timestamp(dt) == "Apr 15, 14:05:09 UTC"


# --- render_as_markdown ---


def test_render_as_markdown_summary_counts():
    result = _result(url_count=10, failures=[_failure()])
    md = render_as_markdown(result)
    assert "Total URLs: **10**" in md
    assert "Successes: **9**" in md
    assert "Failures: **1**" in md


def test_render_as_markdown_table_row_contains_fields():
    result = _result(
        failures=[_failure(url="https://ex.com", handler="MyHandler", message="oops")]
    )
    md = render_as_markdown(result)
    assert "https://ex.com" in md
    assert "MyHandler" in md
    assert "oops" in md


def test_render_as_markdown_escapes_pipe_in_message():
    result = _result(failures=[_failure(message="err|or")])
    assert "err\\|or" in render_as_markdown(result)


def test_render_as_markdown_escapes_pipe_in_url():
    result = _result(failures=[_failure(url="https://ex.com?a=1|2")])
    assert "1\\|2" in render_as_markdown(result)


def test_render_as_markdown_escapes_pipe_in_handler():
    result = _result(failures=[_failure(handler="Han|dler")])
    assert "Han\\|dler" in render_as_markdown(result)


def test_render_as_markdown_zero_failures():
    result = _result(url_count=5, failures=[])
    md = render_as_markdown(result)
    assert "Failures: **0**" in md
    assert "Successes: **5**" in md


def test_render_as_markdown_ends_with_newline():
    assert render_as_markdown(_result()).endswith("\n")


# --- render_as_csv ---


def test_render_as_csv_header():
    rows = list(csv.reader(io.StringIO(render_as_csv([]))))
    assert rows[0] == ["timestamp", "url", "handler", "error"]


def test_render_as_csv_data_row():
    ts = datetime(2026, 4, 2, 14, 5, 9, tzinfo=timezone.utc)
    rows = list(csv.reader(io.StringIO(render_as_csv([_failure(ts=ts)]))))
    assert rows[1] == [ts.isoformat(), "https://example.com", "Handler", "boom"]


def test_render_as_csv_escapes_comma():
    rows = list(
        csv.reader(io.StringIO(render_as_csv([_failure(message="err, comma")])))
    )
    assert rows[1][3] == "err, comma"


def test_render_as_csv_preserves_newline_in_message():
    rows = list(
        csv.reader(io.StringIO(render_as_csv([_failure(message="line1\nline2")])))
    )
    assert rows[1][3] == "line1\nline2"


def test_render_as_csv_empty_failures_header_only():
    rows = list(csv.reader(io.StringIO(render_as_csv([]))))
    assert len(rows) == 1


# --- write_report ---


def test_write_report_writes_content(tmp_path):
    path = tmp_path / "report.md"
    write_report("hello", path)
    assert path.read_text(encoding="utf-8") == "hello"


def test_write_report_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "report.md"
    write_report("content", path)
    assert path.exists()


def test_write_report_utf8(tmp_path):
    path = tmp_path / "report.md"
    write_report("héllo wörld", path)
    assert path.read_text(encoding="utf-8") == "héllo wörld"
